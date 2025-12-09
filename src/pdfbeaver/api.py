# src/pdfbeaver/api.py
"""
Public API for the generic PDF Stream Editor.
"""
# src/pdfbeaver/api.py

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple, Type, Union

import pikepdf
from pdfminer.pdfdevice import PDFDevice
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.pdftypes import PDFStream
from pdfminer.psparser import LIT

from .editor import StreamEditor
from .optimization import optimize_ops

# Import the default registry from the sibling module
from .registry import HandlerRegistry, default_registry
from .state_iterator import StreamStateIterator
from .state_tracker import StateTracker

logger = logging.getLogger(__name__)


@dataclass
class ProcessingOptions:
    """Configuration options for the stream modification process."""

    optimize: bool = True
    """If True, runs a peephole optimizer on the output stream to
    remove dead stores and consolidate arithmetic (e.g., combining
    absolute text matrices into relative moves). Defaults to True.

    """

    recurse_xobjects: bool = True
    """If True, recursively descends into and modifies Form XObjects
    found in the page resources. Defaults to True.

    """

    tracker_class: Type[StateTracker] = StateTracker
    """The class used to track PDF state (Graphics/Text) during
    parsing. Defaults to :class:`StateTracker`.  Users can subclass
    this to add custom logic (e.g., font geometry tracking).

    """

    tracker_args: Tuple = field(default_factory=tuple)
    """Positional arguments passed to the ``tracker_class`` constructor."""

    tracker_kwargs: Dict[str, Any] = field(default_factory=dict)
    """Keyword arguments passed to the ``tracker_class`` constructor."""

    visited_streams: Set[int] = field(default_factory=set)
    """Internal set used to prevent infinite recursion in malformed
    PDFs with cyclic XObject references.

    """


def modify_page(
    pdf: pikepdf.Pdf,
    page: pikepdf.Page,
    handler: HandlerRegistry,
    options: Optional[ProcessingOptions] = None,
) -> None:
    """Modifies a PDF page and (optionally) its Form XObjects in-place.

    This function parses the page's content stream, tracks the graphics and text state,
    and applies the user-defined logic from the ``handler`` registry.

    Args:
        pdf: The owning :class:`pikepdf.Pdf` document. Required to create new
            stream objects when writing back modified content.
        page: The :class:`pikepdf.Page` to modify.
        handler: A :class:`~pdfbeaver.registry.HandlerRegistry` instance containing
            the registered operator callbacks.
        options: Configuration options. If ``None``, defaults are used.

    Returns:
        None: The page is modified in-place.
    """
    if options is None:
        options = ProcessingOptions()

    _modify_content_container(
        pdf=pdf,
        page=page,
        container=page,
        resources=getattr(page, "Resources", {}),
        handler=handler,
        options=options,
    )

    if options.recurse_xobjects:
        _process_child_resources(
            pdf, page, getattr(page, "Resources", {}), handler, options
        )


def _process_child_resources(
    pdf: pikepdf.Pdf,
    page: Optional[pikepdf.Page],
    resources: Any,
    handler: HandlerRegistry,
    options: ProcessingOptions,
) -> None:
    """Recursively finds and modifies Form XObjects within a resource dictionary."""
    if not isinstance(resources, pikepdf.Dictionary) or "/XObject" not in resources:
        return

    xobjects = resources["/XObject"]
    for name, xobj_ref in xobjects.items():
        # Dedup
        try:
            obj_id = xobj_ref.objgen
            if obj_id in options.visited_streams:
                continue
            options.visited_streams.add(obj_id)
        except AttributeError:
            pass

        subtype = xobj_ref.get("/Subtype")
        if subtype != "/Form":
            continue

        logger.debug("Recursing into Form XObject: %s", name)

        try:
            _modify_content_container(
                pdf=pdf,
                page=page,
                container=xobj_ref,
                resources=xobj_ref.get("/Resources", {}),
                handler=handler,
                options=options,
            )
            # Recurse
            _process_child_resources(
                pdf, page, xobj_ref.get("/Resources", {}), handler, options
            )
        except pikepdf.PdfError as e:
            logger.warning("Skipping malformed XObject %s: %s", name, e)


def _make_iterator_with_resources(resources):
    rsrcmgr = PDFResourceManager()
    device = PDFDevice(rsrcmgr)
    iterator = StreamStateIterator(rsrcmgr, device)
    miner_resources = _convert_to_pdfminer_resources(resources)
    iterator.init_resources(miner_resources)
    return iterator


def _modify_content_container(
    resources: Any,
    handler: HandlerRegistry,
    options: ProcessingOptions,
    pdf: Optional[pikepdf.Pdf] = None,
    page: Optional[pikepdf.Page] = None,
    container: Optional[pikepdf.Object] = None,
    is_root: bool = False,
) -> None:
    """Core worker: modifies the content stream of a Page or XObject."""

    iterator = _make_iterator_with_resources(resources)

    stream_list = _get_clean_content_streams(container)
    if not stream_list:
        return

    source_stream = iterator.execute(stream_list)
    tracker = options.tracker_class(*options.tracker_args, **options.tracker_kwargs)
    optimizer_func = optimize_ops if options.optimize else None

    editor = StreamEditor(
        source_iterator=source_stream,
        handler=handler,
        tracker=tracker,
        optimizer=optimizer_func,
        page=page,
        container=container,
        is_page_root=is_root,
    )
    new_bytes = editor.process()

    # Write Back using the PDF object
    # pikepdf.Stream(pdf, data) is the correct constructor for new streams
    if isinstance(container, pikepdf.Page):
        # Page: replace Contents
        # Note: If previously an array, this replaces it with a single consolidated stream.
        # This is generally fine and often preferred.
        container.Contents = pdf.make_stream(new_bytes)
    else:
        # XObject (Stream): update data in place
        container.write(new_bytes)


def _get_clean_content_streams(container: Any) -> List[Any]:
    """
    Return a flat list of clean content streams from a Page, Stream, Array, or raw object.
    """
    raw_contents = _resolve_raw_contents(container)
    items = _normalize_to_list(raw_contents)

    clean_streams: List[Any] = []
    for item in items:
        clean_streams.extend(_process_content_item(item))

    return clean_streams


def _resolve_raw_contents(container: Any) -> Any:
    """Resolve a Page or raw object to its /Contents-compatible form."""
    if isinstance(container, pikepdf.Page):
        try:
            return container.contents
        except (AttributeError, pikepdf.PdfError):
            return container.get("/Contents", [])
    return container


def _normalize_to_list(raw_contents: Any) -> List[Any]:
    """Ensure contents are always returned as a list."""
    if isinstance(raw_contents, (list, pikepdf.Array)):
        return list(raw_contents)
    return [raw_contents]


def _process_content_item(item: Any) -> List[Any]:
    """Process a single content item and return a list of clean streams."""
    # Case: Raw bytes
    if isinstance(item, bytes):
        return [item]

    # Case: Something that can read_bytes (Stream-like or Dictionary-like)
    if hasattr(item, "read_bytes"):
        return _handle_stream_like_item(item)

    # Unknown / irrelevant item
    return []


def _handle_stream_like_item(item: Any) -> List[Any]:
    """Handle Streams, Dictionaries masquerading as streams, and nested Pages."""
    try:
        # Optimization: skip read_bytes if this is a Page dictionary
        if _is_page_dict(item):
            return _extract_page_dict_contents(item)

        return [item]

    except pikepdf.PdfError:
        return _handle_invalid_stream_like(item)


def _is_page_dict(item: Any) -> bool:
    return (
        isinstance(item, pikepdf.Dictionary)
        and "/Type" in item
        and item["/Type"] == "/Page"
    )


def _extract_page_dict_contents(item: pikepdf.Dictionary) -> List[Any]:
    """Extract nested /Contents from a Page dictionary."""
    if "/Contents" in item:
        return _get_clean_content_streams(item["/Contents"])
    return []


def _handle_invalid_stream_like(item: Any) -> List[Any]:
    """Handle Dictionary objects that fail read_bytes but contain /Contents."""
    if isinstance(item, pikepdf.Dictionary) and "/Contents" in item:
        return _get_clean_content_streams(item["/Contents"])

    logger.warning("Skipping invalid content item (not a stream): %r", item)
    return []


def process(
    pdf: pikepdf.Pdf,
    options: Optional[ProcessingOptions] = None,
    registry: Optional[HandlerRegistry] = None,
    pages: Union[None, int, pikepdf.Page, List[Union[int, pikepdf.Page]]] = None,
    page: Union[None, int, pikepdf.Page] = None,
) -> None:
    """High-level entry point to modify PDF content.

    Args:
        pdf: The :class:`pikepdf.Pdf` object to process.
        options: Configuration options.
        registry: The :class:`~pdfbeaver.registry.HandlerRegistry` to use.
            Defaults to the global ``default_registry``.
        pages: The pages to process. Can be a single integer (0-indexed),
            a single Page object, a list of integers/Pages, or None (processes all pages).
        page: Alias for ``pages`` (kept for backward compatibility).

    Raises:
        TypeError: If ``pdf`` is not a pikepdf object or ``pages`` contains invalid types.
    """
    if not isinstance(pdf, pikepdf.Pdf):
        raise TypeError("The 'pdf' argument must be a pikepdf.Pdf object.")

    # Use the global default if none provided
    if registry is None:
        registry = default_registry

    pages_to_process = _resolve_pages(pdf, pages or page)

    for page_to_process in pages_to_process:
        modify_page(pdf, page_to_process, registry, options)


def _resolve_pages(pdf: pikepdf.Pdf, pages_arg) -> List[pikepdf.Page]:
    """Helper to normalize the flexible 'pages' argument."""
    if pages_arg is None:
        return list(pdf.pages)

    if isinstance(pages_arg, int):
        return [pdf.pages[pages_arg]]

    if isinstance(pages_arg, pikepdf.Page):
        return [pages_arg]

    if isinstance(pages_arg, (list, tuple)):
        resolved = []
        for item in pages_arg:
            if isinstance(item, int):
                resolved.append(pdf.pages[item])
            elif isinstance(item, pikepdf.Page):
                resolved.append(item)
            else:
                raise TypeError(f"Invalid item in 'pages' list: {type(item)}")
        return resolved

    raise TypeError(f"Invalid type for 'pages' argument: {type(pages_arg)}")


def _convert_to_pdfminer_resources(obj: Any, strip_slash=False) -> Any:
    """Recursively converts pikepdf resources to types pdfminer understands."""
    result = obj
    if isinstance(obj, pikepdf.Dictionary):
        result = {
            _convert_to_pdfminer_resources(
                k, strip_slash=True
            ): _convert_to_pdfminer_resources(v)
            for k, v in obj.items()
        }
    elif isinstance(obj, pikepdf.Array):
        result = [_convert_to_pdfminer_resources(v) for v in obj]
    elif isinstance(obj, pikepdf.Stream):
        attrs = _convert_to_pdfminer_resources(obj.stream_dict)
        # We pass the original raw (probably compressed) bytes.
        # This is probably not very efficient?
        # Might be better to pass the decompressed bytes (with read_bytes);
        # we'd need to fix up the stream dictionary attrs in that case,
        # at least removing any /Filter.
        result = PDFStream(attrs, obj.read_raw_bytes())
    elif isinstance(obj, (str, pikepdf.String)):
        s = str(obj)
        if strip_slash and s.startswith("/"):
            result = s[1:]
        else:
            result = s
    elif isinstance(obj, pikepdf.Name):
        result = LIT(str(obj)[1:])
    elif isinstance(obj, Decimal):
        result = float(obj)
    return result
