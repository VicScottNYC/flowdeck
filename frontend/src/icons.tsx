import type { SVGProps } from 'react'

const base = (p: SVGProps<SVGSVGElement>) => ({
  width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8,
  strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, ...p,
})

export const IconPulse = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M3 12h4l3-8 4 16 3-8h4" /></svg>
export const IconGrid = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></svg>
export const IconBed = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M3 18v-8M21 18v-5a3 3 0 0 0-3-3h-7v8M3 14h18" /><circle cx="7" cy="12" r="1.5" /></svg>
export const IconDoor = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M14 4h5v16h-5M10 8l4 4-4 4M14 12H3" /></svg>
export const IconClock = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
export const IconTrend = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M3 17l6-6 4 4 8-8M15 7h6v6" /></svg>
export const IconSpark = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z" /></svg>
export const IconShield = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z" /><path d="M9 12l2 2 4-4" /></svg>
export const IconPlug = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M9 7V3M15 7V3M7 7h10v4a5 5 0 0 1-10 0zM12 16v5" /></svg>
export const IconSun = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
export const IconMoon = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M21 13A9 9 0 1 1 11 3a7 7 0 0 0 10 10z" /></svg>
export const IconCheck = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M5 12l5 5L20 7" /></svg>
export const IconAlert = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M12 3l10 18H2zM12 10v4M12 17.5v.5" /></svg>
export const IconSend = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M4 12l16-8-6 16-2-7z" /></svg>
