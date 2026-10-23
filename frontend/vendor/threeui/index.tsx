// Kage export copied verbatim from the registered LandingPages.tsx.
// The complete upstream module is retained alongside its dependencies.
import { splitTypographyProps, usePageTypography, type PageTypographyProps } from "./src/shaders/landing-pages/pageTypography";
import { LandingPageFrame, type LandingPageProps } from "./src/shaders/landing-pages/LandingPageFrame";
import { KAGE_TYPOGRAPHY } from "./src/shaders/landing-pages/pageRecipes";

export function KageLandingPage(props: LandingPageProps & PageTypographyProps) {
  const [type, frame] = splitTypographyProps(props);
  const customization = usePageTypography(KAGE_TYPOGRAPHY, type);
  return <LandingPageFrame {...frame} customization={customization} title="Kage — Where stillness reveals the unseen" sourceUrl="/landing-pages/kage.html" />;
}
