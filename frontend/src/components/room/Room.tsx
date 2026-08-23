import './room.css';
import { buildRoomView, type RoomProps } from './model';

/**
 * The stagger, in the order the annotation names: **the room assembles,
 * argues, and reports.**
 *
 * One orchestrated moment, not scattered micro-interactions — the eyebrow, then
 * the stage, then the objections landing under it one at a time, then the
 * measured numbers. `room.css` collapses all of it under
 * `prefers-reduced-motion: reduce`, so these delays are a schedule for people
 * who asked for motion and are irrelevant to everyone else.
 *
 * Timings are CSS, not data. They are the only numbers in this file, and they
 * describe when a thing appears rather than what it says.
 */
const EYEBROW_AT = 0.05;
const STAGE_AT = 0.18;
const FIRST_ROW_AT = 0.54;
const ROW_STEP = 0.12;
const NOTE_AT = 0.86;
const FIRST_STAT_AT = 0.94;
const STAT_STEP = 0.08;

const after = (seconds: number): string => `${seconds.toFixed(2)}s`;

/**
 * The room, inside the app — the landing page's hero where the founder paid
 * for it.
 *
 * `design/canvas.json`, annotation `the-room`: the landing page's hero is a
 * room of buyers orbiting a pitch, and inside the app that same room has
 * always been a table of numbers. This is the room, drawn from the run's own
 * measured values.
 *
 * **Nothing here is decoration standing in for data.** Every count, label and
 * number is built by `buildRoomView` out of the props and omitted when the
 * prop is absent; this file holds no copy and no arithmetic of its own, so
 * there is nowhere for a plausible-looking default to enter. The two orbit
 * rings are the room's frame and are drawn identically on every run — they are
 * not a reading of anything and do not claim to be.
 *
 * Renders nothing at all when the run carried nothing measurable.
 */
export default function Room(props: RoomProps) {
  const view = buildRoomView(props);
  if (view.isEmpty) return null;

  const { console: pushback } = view;

  return (
    <div className={props.className ? `sbroom ${props.className}` : 'sbroom'}>
      <div className="sbroom-eyebrow sbroom-rise" style={{ animationDelay: after(EYEBROW_AT) }}>
        {view.eyebrow}
      </div>

      <div className="sbroom-stage sbroom-arrive" style={{ animationDelay: after(STAGE_AT) }}>
        <div className="sbroom-orbit sbroom-orbit-two" aria-hidden="true">
          <i />
        </div>
        <div className="sbroom-orbit sbroom-orbit-one" aria-hidden="true">
          <i />
        </div>

        <div className="sbroom-core">
          <div className="sbroom-core-inner">
            <div className="sbroom-core-label">{view.pitchLabel}</div>
            {view.pitchName !== null && (
              <strong className="sbroom-core-name">{view.pitchName}</strong>
            )}
            {view.pitchMeta !== null && (
              <b className="sbroom-core-meta">{view.pitchMeta}</b>
            )}
          </div>
        </div>

        {view.chips.map((chip, index) => (
          <div key={chip.key} className={`sbroom-chip sbroom-slot-${index}`}>
            <span
              className="sbroom-chip-avatar"
              style={{ color: chip.fg, background: chip.bg }}
              aria-hidden="true"
            >
              {chip.initials}
            </span>
            <span className="sbroom-chip-text">
              <b className="sbroom-chip-name">{chip.label}</b>
              {chip.meta !== null && <small className="sbroom-chip-meta">{chip.meta}</small>}
            </span>
          </div>
        ))}

        {pushback !== null && (
          <div className="sbroom-console">
            <div className="sbroom-console-top">
              <span>{pushback.title}</span>
              <span className="sbroom-live">
                <i aria-hidden="true" />
                {pushback.found}
              </span>
            </div>
            {pushback.rows.map((row, index) => (
              <div
                key={row.key}
                className="sbroom-row sbroom-rise"
                style={{ animationDelay: after(FIRST_ROW_AT + index * ROW_STEP) }}
              >
                <i style={{ background: row.color }} aria-hidden="true" />
                <span>{row.label}</span>
                {row.meta !== null && <b>{row.meta}</b>}
              </div>
            ))}
          </div>
        )}
      </div>

      {view.note !== null && (
        <p className="sbroom-note sbroom-rise" style={{ animationDelay: after(NOTE_AT) }}>
          {view.note}
        </p>
      )}

      {view.stats.length > 0 && (
        <div className="sbroom-stats">
          {view.stats.map((stat, index) => (
            <div
              key={stat.key}
              className="sbroom-stat sbroom-rise"
              style={{ animationDelay: after(FIRST_STAT_AT + index * STAT_STEP) }}
            >
              <div className="sbroom-stat-top">
                <span
                  className="sbroom-stat-dot"
                  style={{ background: stat.dot }}
                  aria-hidden="true"
                />
                <span className="sbroom-stat-label">{stat.label}</span>
              </div>
              <div className="sbroom-stat-value">{stat.value}</div>
              {stat.note !== null && <p className="sbroom-stat-note">{stat.note}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
