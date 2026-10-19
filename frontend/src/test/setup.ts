import "@testing-library/jest-dom/vitest";

// Recharts' ResponsiveContainer requires ResizeObserver, which jsdom lacks.
class ResizeObserverMock {
  callback: ResizeObserverCallback;
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }
  observe(target: Element) {
    const entries = [
      {
        target,
        contentRect: {
          width: 500,
          height: 250,
          top: 0,
          left: 0,
          bottom: 0,
          right: 0,
          x: 0,
          y: 0,
        },
      } as unknown as ResizeObserverEntry,
    ];
    this.callback(entries, this);
  }
  unobserve() {}
  disconnect() {}
}

if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;
}
