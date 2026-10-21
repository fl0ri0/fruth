"""Native MLX-VLM image serving with completed-request residency cleanup.

Run with the native MLX interpreter. Importing this module does not import MLX,
Fruth runtime, models or state. The native server still owns all HTTP contracts.
"""
from __future__ import annotations

import gc
import logging
import sys
import time


LOGGER = logging.getLogger("fruth.mlx_image_server")
IMAGE_PATHS = frozenset({
    "/images/generations", "/v1/images/generations",
    "/images/edits", "/v1/images/edits",
})
IMAGE_CACHE_GROUPS = ("image_generation", "image_edit")


def release_image_cache(mx, *, unload=None):
    """Release idle image ownership through the native owner, then unused buffers.

    The caller must ensure no image request is using either image cache group.
    Without an unload callback this retains the allocator-only operation.
    """
    started = time.perf_counter()
    mx.synchronize()
    active_before = mx.get_active_memory()
    before = mx.get_cache_memory()
    unloaded = []
    if unload is not None:
        for group in IMAGE_CACHE_GROUPS:
            if unload(group):
                unloaded.append(group)
    gc.collect()
    mx.clear_cache()
    LOGGER.info(
        "Image request cache released: cache_before_bytes=%d cache_after_bytes=%d "
        "active_after_bytes=%d elapsed_s=%.6f active_before_bytes=%d unloaded_groups=%s",
        before, mx.get_cache_memory(), mx.get_active_memory(),
        time.perf_counter() - started, active_before, ",".join(unloaded) or "none",
    )


class ImageRequestCleanup:
    """Release idle image models without buffering or rewriting native responses.

    The ASGI event loop owns the request count. Cleanup is synchronous and only
    runs when all other image requests have left the native app. This covers
    generation and editing together, including requests awaiting input/delivery.
    """

    def __init__(self, app, *, cleanup):
        self.app = app
        self.cleanup = cleanup
        self.active_requests = 0
        self.cleanup_pending = False

    def _cleanup(self):
        self.cleanup_pending = False
        try:
            self.cleanup()
        except Exception:
            # Cleanup must not replace output/errors or cause generation retries.
            LOGGER.exception("Image request cache cleanup failed")

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope.get("method") != "POST"
                or scope.get("path") not in IMAGE_PATHS):
            return await self.app(scope, receive, send)

        self.active_requests += 1
        self.cleanup_pending = True
        cleaned = False

        async def send_response(message):
            nonlocal cleaned
            if (message["type"] == "http.response.start" and not cleaned
                    and 200 <= message["status"] < 300 and self.active_requests == 1):
                cleaned = True
                # Native image endpoints return materialized JSON, not streams.
                # PNG/path serialization is done. No other image request
                # owns the cache; native lazy loading handles the next request.
                self._cleanup()
            await send(message)

        try:
            return await self.app(scope, receive, send_response)
        finally:
            self.active_requests -= 1
            if self.cleanup_pending and self.active_requests == 0:
                # Also cover native exceptions, cancellation and overlapping
                # deliveries which deferred the before-headers cleanup.
                self._cleanup()


def main():
    # Native reload starts another interpreter and would bypass this launcher.
    if "--reload" in sys.argv[1:]:
        raise SystemExit("The Fruth MLX image launcher does not support --reload.")
    if "--image-model" not in sys.argv[1:]:
        raise SystemExit("The Fruth MLX image launcher requires --image-model.")
    import mlx.core as mx
    import mlx_vlm.server as server

    unload = getattr(server, "_unload_model_cache_group", None)
    if not callable(unload):
        raise SystemExit("The MLX image launcher requires native per-kind model unloading.")
    server.app.add_middleware(ImageRequestCleanup,
                              cleanup=lambda: release_image_cache(mx, unload=unload))
    server.main()


if __name__ == "__main__":
    main()
