from collections import Counter
import math

import pytest
from blender_mcp.recipes import lathe_data


def edges(faces):
    return Counter(tuple(sorted((a,b))) for face in faces for a,b in zip(face,face[1:]+face[:1]))


def test_hollow_jar_has_welded_seam_single_poles_and_closed_topology():
    data = lathe_data([(0,0),(.04,0),(.04,.08),(.037,.08),(.037,.003),(0,.003),(0,0)], segments=16)
    vertices, faces, uvs, _ = data
    assert len(vertices) == 4*16+2
    assert set(edges(faces).values()) == {2}
    assert all(len(set(face)) == len(face) for face in faces)
    # Each geometric seam vertex is shared; adjacent UV corners may be 0 or 1.
    assert min(u for row in uvs for u,v in row) == 0
    assert max(u for row in uvs for u,v in row) == 1


def test_closed_annular_profile_has_no_duplicate_ring_or_boundary():
    profile = [(1+.1*math.cos(i*math.tau/8), .1*math.sin(i*math.tau/8)) for i in range(8)]
    profile.append(profile[0])
    vertices, faces, _, _ = lathe_data(profile,segments=16)
    assert len(vertices) == 8*16
    assert set(edges(faces).values()) == {2}


@pytest.mark.parametrize('profile,options', [
    ([(0,0),(1,1)], {'segments':513}),
    ([(0,0),(float('nan'),1)], {}),
    ([(0,0),(1,1),(1,1)], {}),
    ([(0,0),(1,1)], {'surfaces':{0:(0,'unknown')}}),
])
def test_invalid_geometry_is_rejected_before_mesh_creation(profile, options):
    with pytest.raises(ValueError):
        lathe_data(profile, **options)
