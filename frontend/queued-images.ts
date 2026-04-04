/*
 * AUTO-GENERATED OUTPUT WARNING:
 * Do not edit the generated static/*.js files directly.
 * Make changes in frontend/*.ts and rebuild.
 * FANIC_ASSET_VERSION: 20260404
 */

(() => {
  const IMAGE_SELECTOR = "img[data-queued-src]";
  const MAX_PARALLEL_LOADS = 8;
  const ROOT_MARGIN = "300px 0px";

  let activeLoads = 0;
  const queue: HTMLImageElement[] = [];
  const queued = new WeakSet<HTMLImageElement>();
  const loaded = new WeakSet<HTMLImageElement>();

  function finishLoad(): void {
    activeLoads = Math.max(0, activeLoads - 1);
    pumpQueue();
  }

  function startLoad(image: HTMLImageElement): void {
    if (loaded.has(image)) {
      return;
    }

    const src = image.dataset.queuedSrc ? image.dataset.queuedSrc : "";
    if (!src) {
      return;
    }

    loaded.add(image);
    activeLoads += 1;
    image.addEventListener("load", finishLoad, { once: true });
    image.addEventListener("error", finishLoad, { once: true });
    image.src = src;
    image.removeAttribute("data-queued-src");
  }

  function pumpQueue(): void {
    while (activeLoads < MAX_PARALLEL_LOADS && queue.length > 0) {
      const image = queue.shift();
      if (!image) {
        break;
      }
      if (!image.isConnected) {
        continue;
      }
      startLoad(image);
    }
  }

  function queueImage(image: HTMLImageElement): void {
    if (loaded.has(image) || queued.has(image)) {
      return;
    }
    queued.add(image);
    queue.push(image);
    pumpQueue();
  }

  function init(): void {
    const images = Array.from(document.querySelectorAll<HTMLImageElement>(IMAGE_SELECTOR));
    if (images.length === 0) {
      return;
    }

    if (!("IntersectionObserver" in window)) {
      images.forEach((image) => queueImage(image));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) {
            return;
          }
          const target = entry.target;
          if (!(target instanceof HTMLImageElement)) {
            return;
          }
          observer.unobserve(target);
          queueImage(target);
        });
      },
      {
        root: null,
        rootMargin: ROOT_MARGIN,
        threshold: 0.01,
      },
    );

    images.forEach((image) => observer.observe(image));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
