'use client';

import { useEffect, useRef } from 'react';

export function CanvasAsciiBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
      
      // Re-configure font on resize
      if (ctx) {
        ctx.font = `${fontSize}px 'Courier New', Courier, monospace`;
      }
    };
    window.addEventListener('resize', handleResize);

    // Grid config
    const fontSize = 11;
    ctx.font = `${fontSize}px 'Courier New', Courier, monospace`;
    let cols = Math.ceil(width / (fontSize * 0.75));
    let rows = Math.ceil(height / (fontSize * 1.3));

    let time = 0;
    const render = () => {
      ctx.clearRect(0, 0, width, height);
      time += 0.03; // Slow, premium ambient motion

      const currentCols = Math.ceil(width / (fontSize * 0.75));
      const currentRows = Math.ceil(height / (fontSize * 1.3));

      if (currentCols !== cols || currentRows !== rows) {
        cols = currentCols;
        rows = currentRows;
      }

      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const x = c * fontSize * 0.75;
          const y = r * fontSize * 1.3;

          // Normalized coordinates
          const nx = c / cols;
          const ny = r / rows;

          // Multi-frequency wave octaves for cloud density
          const wave1 = Math.sin(nx * 3.5 + time * 0.15) * Math.cos(ny * 2.5);
          const wave2 = Math.sin(nx * 7.5 - time * 0.25) * Math.cos(ny * 4.5) * 0.5;
          const wave3 = Math.sin((nx + ny) * 12.0 + time * 0.08) * 0.2;
          
          // Dither sky bias: denser at the top, fading down
          const baseDensity = 0.55 - (ny * 0.45); 
          const density = baseDensity + (wave1 + wave2 + wave3) * 0.38;

          // Map cloud density to dithered symbols matching the sky image
          let char = ' ';
          if (density > 0.82) {
            char = '█';
          } else if (density > 0.68) {
            char = '▓';
          } else if (density > 0.54) {
            char = '▒';
          } else if (density > 0.40) {
            char = '░';
          } else if (density > 0.28) {
            char = '％';
          } else if (density > 0.18) {
            char = '＋';
          } else if (density > 0.08) {
            char = '：';
          } else if (density > 0.02) {
            char = '·';
          }

          if (char !== ' ') {
            // Render in requested #2A2529 (rgb: 42, 37, 41) with subtle transparency
            const opacity = 0.04 + (density * 0.08); 
            ctx.fillStyle = `rgba(42, 37, 41, ${opacity})`;
            ctx.fillText(char, x, y);
          }
        }
      }

      animationId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animationId);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 h-full w-full opacity-90"
    />
  );
}
