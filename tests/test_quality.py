import numpy as np

from blender_mcp.quality import compare_pixels, foreground_mask


def product(x=4, alpha=False):
    image = np.ones((20, 20, 4), dtype=np.float32)
    if alpha:
        image[..., 3] = 0
    image[3:17, x:x+10, :3] = .4
    image[3:17, x:x+10, 3] = 1
    return image


def test_reference_comparison_does_not_hide_alignment_error():
    matched = compare_pixels(product(), product(alpha=True))
    shifted = compare_pixels(product(), product(6, alpha=True))
    assert matched['silhouette_iou'] == 1
    assert matched['foreground_rgb_mae'] == 0
    assert shifted['silhouette_iou'] < 1
    assert shifted['bbox_delta_px'] == [2, 0, 2, 0]


def test_white_label_is_not_a_hole_in_product_silhouette():
    image = product()
    image[7:10, 8:11, :3] = 1
    assert foreground_mask(image).sum() == 140


def test_comparison_declines_blank_or_differently_sized_images():
    assert not compare_pixels(np.ones((20, 20, 4)), product())['comparable']
    assert not compare_pixels(product(), product()[:10])['comparable']
