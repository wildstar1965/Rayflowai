"""Normalized rectangles also implemented in frontend/utils/composition.ts."""

def insert_rect(mode, position):
    if mode in ('cutaway', 'background'):
        return (0, 0, 1, 1)
    if mode == 'split':
        return (0.5, 0, 0.5, 1)
    # Fixed, bounded frame avoids portrait assets obscuring captions.
    return {'top_left': (.05, .08, .38, .24),
            'bottom_right': (.57, .55, .38, .24),
            'center': (.31, .32, .38, .24)}.get(position, (.57, .08, .38, .24))
