/**
 * The app's design system, in one import.
 *
 *   import { PageHeader, Eyebrow, Card, Rise, Deal, Ground } from '@/components/design';
 *
 * A barrel rather than six paths, because the point of lifting this out of the
 * design canvas was that a page should not have to know which file a rule lives
 * in. The stylesheet (`design.css`) travels with the components, so importing
 * anything here brings the system's CSS with it.
 */
export {
  Card,
  Deal,
  Eyebrow,
  Ground,
  PageHeader,
  Rise,
} from './DesignPrimitives';

export {
  cardSurface,
  dealDelayMs,
  DEAL_MAX_STEPS,
  DEAL_STEP_MS,
  type CardCarries,
} from './surfaces';
