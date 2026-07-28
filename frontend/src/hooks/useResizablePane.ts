import { useCallback, useEffect, useRef, useState } from 'react'

/** Reactively tracks whether a CSS media query matches the current viewport. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia(query).matches : false,
  )
  useEffect(() => {
    const mql = window.matchMedia(query)
    const onChange = () => setMatches(mql.matches)
    onChange()
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [query])
  return matches
}

interface ResizablePaneOptions {
  /** Initial right-pane fraction of the container width (0–1). */
  initialRatio?: number
  /** Clamp bounds for the right-pane fraction. */
  min?: number
  max?: number
}

interface ResizablePane {
  containerRef: React.RefObject<HTMLDivElement | null>
  /** Right-pane fraction of the container width. */
  ratio: number
  onHandleMouseDown: (e: React.MouseEvent) => void
  dragging: boolean
}

/**
 * Drives a draggable vertical divider where the *right* pane is the sized one.
 * The divider tracks the pointer's distance from the container's right edge,
 * clamped to [min, max], so dragging left widens the right pane.
 */
export function useResizablePane({
  initialRatio = 0.5,
  min = 0.28,
  max = 0.72,
}: ResizablePaneOptions = {}): ResizablePane {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [ratio, setRatio] = useState(initialRatio)
  const [dragging, setDragging] = useState(false)
  const draggingRef = useRef(false)

  const onHandleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    draggingRef.current = true
    setDragging(true)
  }, [])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const el = containerRef.current
      if (!draggingRef.current || !el) return
      const rect = el.getBoundingClientRect()
      if (rect.width === 0) return
      const fromRight = rect.right - e.clientX
      setRatio(Math.min(max, Math.max(min, fromRight / rect.width)))
    }
    const stop = () => {
      if (!draggingRef.current) return
      draggingRef.current = false
      setDragging(false)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', stop)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', stop)
    }
  }, [min, max])

  return { containerRef, ratio, onHandleMouseDown, dragging }
}
