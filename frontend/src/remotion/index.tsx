import { Composition } from 'remotion';
import { SaibylHero } from './SaibylHero';

export const RemotionRoot: React.FC = () => (
  <Composition
    id="SaibylHero"
    component={SaibylHero}
    durationInFrames={480}
    fps={30}
    width={1920}
    height={1080}
    defaultProps={{}}
  />
);
