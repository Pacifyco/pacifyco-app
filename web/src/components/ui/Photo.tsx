import type { CSSProperties } from "react";
import parentsDinnerCouple640 from "../../assets/photos/parents-dinner-couple-640.jpg";
import parentsDinnerCouple1200 from "../../assets/photos/parents-dinner-couple-1200.jpg";
import parentsDinnerFriends640 from "../../assets/photos/parents-dinner-friends-640.jpg";
import parentsDinnerFriends1200 from "../../assets/photos/parents-dinner-friends-1200.jpg";
import sitterBlocks640 from "../../assets/photos/sitter-blocks-640.jpg";
import sitterBlocks1200 from "../../assets/photos/sitter-blocks-1200.jpg";
import sitterBubbles640 from "../../assets/photos/sitter-bubbles-640.jpg";
import sitterBubbles1200 from "../../assets/photos/sitter-bubbles-1200.jpg";
import sitterCrafts640 from "../../assets/photos/sitter-crafts-640.jpg";
import sitterCrafts1200 from "../../assets/photos/sitter-crafts-1200.jpg";
import sitterHomePlay640 from "../../assets/photos/sitter-home-play-640.jpg";
import sitterHomePlay1200 from "../../assets/photos/sitter-home-play-1200.jpg";
import sitterSlide640 from "../../assets/photos/sitter-slide-640.jpg";
import sitterSlide1200 from "../../assets/photos/sitter-slide-1200.jpg";
import { cx } from "./cx";

// design.md section 8. Interim photos from /assets (children's faces covered) until the commissioned
// photography arrives; swap the files here and every page follows. `focus` keeps faces in frame when
// the photo is cropped to the requested shape.
const PHOTOS = {
  parentsDinnerCouple: { small: parentsDinnerCouple640, large: parentsDinnerCouple1200, focus: "50% 30%" },
  parentsDinnerFriends: { small: parentsDinnerFriends640, large: parentsDinnerFriends1200, focus: "55% 35%" },
  sitterBlocks: { small: sitterBlocks640, large: sitterBlocks1200, focus: "55% 45%" },
  sitterBubbles: { small: sitterBubbles640, large: sitterBubbles1200, focus: "50% 40%" },
  sitterCrafts: { small: sitterCrafts640, large: sitterCrafts1200, focus: "50% 45%" },
  sitterHomePlay: { small: sitterHomePlay640, large: sitterHomePlay1200, focus: "50% 45%" },
  sitterSlide: { small: sitterSlide640, large: sitterSlide1200, focus: "50% 35%" },
} as const;

export type PhotoName = keyof typeof PHOTOS;

type PhotoProps = {
  name: PhotoName;
  /** Width / height, e.g. "16 / 9". */
  aspect?: string;
  /** How wide it shows on large screens, for picking the right file. */
  sizes?: string;
  /** Load straight away (photos at the top of a page). */
  priority?: boolean;
  className?: string;
};

/** A decorative photo: rounded, gently fades in, never carries information (so alt=""). */
export function Photo({ name, aspect = "16 / 9", sizes = "(min-width: 640px) 36rem, 100vw", priority, className }: PhotoProps) {
  const photo = PHOTOS[name];
  const style: CSSProperties = { aspectRatio: aspect, objectPosition: photo.focus };
  return (
    <img
      src={photo.small}
      srcSet={`${photo.small} 640w, ${photo.large} 1200w`}
      sizes={sizes}
      alt=""
      loading={priority ? "eager" : "lazy"}
      decoding="async"
      style={style}
      className={cx("photo-in block w-full rounded-lg bg-surface-sunken object-cover shadow-soft", className)}
    />
  );
}
