import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useCountdown } from './useCountdown';

describe('useCountdown', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should initialize with countdown=0 and isCounting=false', () => {
    const { result } = renderHook(() => useCountdown());
    expect(result.current.countdown).toBe(0);
    expect(result.current.isCounting).toBe(false);
  });

  it('should start countdown with default 60 seconds', () => {
    const { result } = renderHook(() => useCountdown());

    act(() => {
      result.current.start();
    });

    expect(result.current.countdown).toBe(60);
    expect(result.current.isCounting).toBe(true);
  });

  it('should start countdown with custom seconds', () => {
    const { result } = renderHook(() => useCountdown(30));

    act(() => {
      result.current.start();
    });

    expect(result.current.countdown).toBe(30);
    expect(result.current.isCounting).toBe(true);
  });

  it('should decrement countdown every second', () => {
    const { result } = renderHook(() => useCountdown(5));

    act(() => {
      result.current.start();
    });

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current.countdown).toBe(4);

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current.countdown).toBe(3);
  });

  it('should stop when countdown reaches 0', () => {
    const { result } = renderHook(() => useCountdown(3));

    act(() => {
      result.current.start();
    });

    act(() => {
      vi.advanceTimersByTime(3000);
    });

    expect(result.current.countdown).toBe(0);
    expect(result.current.isCounting).toBe(false);
  });

  it('should allow restarting after countdown finishes', () => {
    const { result } = renderHook(() => useCountdown(2));

    act(() => {
      result.current.start();
    });

    act(() => {
      vi.advanceTimersByTime(2000);
    });

    expect(result.current.isCounting).toBe(false);

    act(() => {
      result.current.start();
    });

    expect(result.current.countdown).toBe(2);
    expect(result.current.isCounting).toBe(true);
  });

  it('should reset when start is called during active countdown', () => {
    const { result } = renderHook(() => useCountdown(10));

    act(() => {
      result.current.start();
    });

    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(result.current.countdown).toBe(7);

    act(() => {
      result.current.start();
    });
    expect(result.current.countdown).toBe(10);
  });

  it('should clean up interval on unmount', () => {
    const clearIntervalSpy = vi.spyOn(globalThis, 'clearInterval');
    const { result, unmount } = renderHook(() => useCountdown(60));

    act(() => {
      result.current.start();
    });

    unmount();
    expect(clearIntervalSpy).toHaveBeenCalled();
    clearIntervalSpy.mockRestore();
  });
});
