// Drag handle for resizing the columns flanking it. Persists width to localStorage.

import { useEffect, useRef } from "react";

interface Props {
  /** Direction of the drag motion that changes width (always horizontal here). */
  side: "left" | "right";
  width: number;
  setWidth: (next: number) => void;
  min?: number;
  max?: number;
}

/** A 6px-wide vertical bar. Dragging right increases width when side="left",
 *  decreases width when side="right". */
export function ResizeHandle({ side, width, setWidth, min = 160, max = 900 }: Props) {
  const widthRef = useRef(width);
  widthRef.current = width;

  useEffect(() => {
    widthRef.current = width;
  }, [width]);

  const onPointerDown = (e: React.PointerEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = widthRef.current;

    const move = (ev: PointerEvent) => {
      const dx = ev.clientX - startX;
      const next = side === "left" ? startW + dx : startW - dx;
      setWidth(Math.max(min, Math.min(max, next)));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  return <div className="resize-handle" onPointerDown={onPointerDown} />;
}
