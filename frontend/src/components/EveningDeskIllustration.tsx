import styles from './EveningDeskIllustration.module.css'

/**
 * Locked motif: promo/welcome-desk-reference.png (+ photo_4 layout).
 * Moon = cream disk + visible dark disk offset right → thick left crescent.
 */
export function EveningDeskIllustration() {
  return (
    <div className={styles.wrap} aria-hidden="true">
      <svg
        className={styles.svg}
        viewBox="0 0 390 280"
        xmlns="http://www.w3.org/2000/svg"
        role="presentation"
      >
        <defs>
          <linearGradient id="pd-sky" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#1e212c" />
            <stop offset="55%" stopColor="#242831" />
            <stop offset="100%" stopColor="#2d323e" />
          </linearGradient>
          <radialGradient id="pd-lamp-glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#e7c79c" stopOpacity="0.38" />
            <stop offset="55%" stopColor="#e7c79c" stopOpacity="0.1" />
            <stop offset="100%" stopColor="#e7c79c" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="pd-cone" x1="50%" y1="0%" x2="50%" y2="100%">
            <stop offset="0%" stopColor="#e7c79c" stopOpacity="0.48" />
            <stop offset="42%" stopColor="#d4b483" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#e7c79c" stopOpacity="0" />
          </linearGradient>
          <clipPath id="pd-window-clip">
            <circle cx="120" cy="124" r="100" />
          </clipPath>
        </defs>

        <rect width="390" height="280" fill="#1a1a1a" />

        {/* Window frame */}
        <circle cx="120" cy="124" r="110" fill="#3b3b3f" />
        <circle cx="120" cy="124" r="100" fill="url(#pd-sky)" />

        {/* Sky contents clipped to glass */}
        <g clipPath="url(#pd-window-clip)">
          {/* Moon: cream disk + visible dark disk (eclipse / earthshine look) */}
          <circle cx="92" cy="88" r="38" fill="#eae7dc" />
          <circle cx="110" cy="80" r="34" fill="#242831" />

          {/* Four-pointed stars + tiny dots — cream like the moon */}
          <g fill="#eae7dc">
            <path d={starPath(48, 78, 7)} opacity="0.95" />
            <path d={starPath(148, 58, 8)} opacity="0.95" />
            <path d={starPath(168, 98, 5)} opacity="0.85" />
            <path d={starPath(158, 148, 6)} opacity="0.8" />
            <path d={starPath(62, 158, 4.5)} opacity="0.75" />
            <circle cx="132" cy="48" r="1.6" opacity="0.85" />
            <circle cx="178" cy="128" r="1.2" opacity="0.7" />
            <circle cx="70" cy="48" r="1.1" opacity="0.65" />
          </g>
        </g>

        {/* Horizontal mullion — after sky so it sits on top */}
        <rect x="20" y="118" width="200" height="12" rx="2" fill="#3b3b3f" />

        {/* Lamp glow + cone */}
        <ellipse className={styles.glow} cx="255" cy="36" rx="72" ry="46" fill="url(#pd-lamp-glow)" />
        <path
          className={styles.cone}
          d="M218 34 L292 34 L342 250 L168 250 Z"
          fill="url(#pd-cone)"
        />
        <line
          x1="255"
          y1="0"
          x2="255"
          y2="20"
          stroke="#5a5552"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
        <path d="M216 30 C216 12 233 2 255 2 C277 2 294 12 294 30 Z" fill="#3c393b" />
        <ellipse cx="255" cy="30" rx="39" ry="6.5" fill="#2b292b" />
        <ellipse cx="255" cy="30" rx="26" ry="3" fill="#e7c79c" opacity="0.28" />

        {/* Open notebook */}
        <g transform="translate(142 162)">
          <path
            d="M0 10 C10 2 22 0 34 0 H98 L108 5 V84 H34 C20 84 8 76 0 66 Z"
            fill="#ebe6e0"
          />
          <path
            d="M108 5 L118 0 H180 C192 0 202 2 212 10 V66 C204 76 192 84 180 84 H108 Z"
            fill="#ebe6e0"
          />
          <path d="M108 5 V84" stroke="#d2c8c0" strokeWidth="2.5" />
          <path
            d="M26 20 H90 M26 32 H86 M26 44 H88 M26 56 H84 M26 68 H80"
            stroke="#8a8580"
            strokeWidth="2.4"
            strokeLinecap="round"
          />
          <path
            d="M126 20 H192 M126 32 H188 M126 44 H190 M126 56 H184 M126 68 H186"
            stroke="#8a8580"
            strokeWidth="2.4"
            strokeLinecap="round"
          />
        </g>

        {/* Mug + steam */}
        <g transform="translate(72 182)">
          <rect x="0" y="12" width="42" height="40" rx="5" fill="#4d4d4d" />
          <path
            d="M42 20 H54 C60 20 62 24 62 30 C62 36 60 40 54 40 H42"
            fill="none"
            stroke="#4d4d4d"
            strokeWidth="5.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            className={styles.steam}
            d="M12 8 C10 2 16 0 14 -6"
            fill="none"
            stroke="#6e6a6d"
            strokeWidth="2.2"
            strokeLinecap="round"
            opacity="0.75"
          />
          <path
            className={styles.steamDelay}
            d="M28 8 C26 3 32 1 30 -5"
            fill="none"
            stroke="#6e6a6d"
            strokeWidth="2.2"
            strokeLinecap="round"
            opacity="0.55"
          />
        </g>

        {/* Pen on notebook corner */}
        <g transform="translate(300 232) rotate(-28)">
          <rect x="0" y="0" width="48" height="7" rx="2" fill="#4d4d4d" />
          <path d="M48 0 L60 3.5 L48 7 Z" fill="#2a282a" />
        </g>
      </svg>
    </div>
  )
}

/** Simple 4-point diamond star centered at (cx, cy). */
function starPath(cx: number, cy: number, size: number): string {
  const tip = size
  const mid = size * 0.28
  return [
    `M${cx} ${cy - tip}`,
    `L${cx + mid} ${cy - mid}`,
    `L${cx + tip} ${cy}`,
    `L${cx + mid} ${cy + mid}`,
    `L${cx} ${cy + tip}`,
    `L${cx - mid} ${cy + mid}`,
    `L${cx - tip} ${cy}`,
    `L${cx - mid} ${cy - mid}`,
    'Z',
  ].join(' ')
}
