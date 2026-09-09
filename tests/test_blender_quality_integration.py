"""Optional real-Blender regressions; set BLENDER_BINARY to enable."""
import json
import os
from pathlib import Path
import time

import pytest
from blender_mcp.workers import WorkerManager

BINARY = os.getenv('BLENDER_BINARY')
pytestmark = pytest.mark.skipif(not BINARY, reason='Set BLENDER_BINARY for real Blender checks')


def test_background_audit_finds_defects_and_preserves_valid_geometry(tmp_path):
    script = tmp_path/'fixture.py'
    script.write_text('''import bpy
from better_blender import lathe, pbr_material
bpy.ops.wm.read_factory_settings(use_empty=True)
material, shader = pbr_material('Paint')
solid = lathe('ClosedSolid', [(0,0),(1,0),(1,2),(.9,2),(.9,.1),(0,.1),(0,0)], materials=[material], segments=32)
bpy.ops.mesh.primitive_plane_add()
sheet = bpy.context.object
sheet.name = 'BrokenSheet'
mat = bpy.data.materials.new('Unbaked')
mat.use_nodes = True
sheet.data.materials.append(mat)
p = mat.node_tree.nodes.get('Principled BSDF')
n = mat.node_tree.nodes.new('ShaderNodeTexNoise')
mat.node_tree.links.new(n.outputs['Fac'], p.inputs['Roughness'])
tex = mat.node_tree.nodes.new('ShaderNodeTexImage')
tex.image = bpy.data.images.new('Detail', width=8, height=8)
mat.node_tree.links.new(tex.outputs['Color'], p.inputs['Base Color'])
for loop in sheet.data.uv_layers.active.data:
    loop.uv = (0,0)
''', encoding='utf-8')
    manager = WorkerManager(tmp_path/'jobs')
    try:
        job = manager.start(BINARY, script, timeout_seconds=30, job_id='a'*32)
        same = manager.start(BINARY, script, timeout_seconds=30, job_id='a'*32)
        assert same['pid'] == job['pid']
        done = manager.wait(job['id'], 30)
        assert done['state'] == 'succeeded', done
        audit = done['result']['audit']
        assert {'OPEN_BOUNDARY', 'UV_COLLAPSED', 'GLTF_BAKE_REQUIRED'} <= audit['issue_counts'].keys()
        assert not any(i['target'] == 'ClosedSolid' for i in audit['issues'])
        full = json.loads(Path(done['result_path']).read_text(encoding='utf-8'))
        assert len(full['audit']['objects']) == 2
        assert WorkerManager(tmp_path/'jobs').start(BINARY, script, timeout_seconds=30, job_id='a'*32)['pid'] == job['pid']
        script.write_text('raise RuntimeError("changed")', encoding='utf-8')
        with pytest.raises(ValueError, match='different inputs'):
            manager.start(BINARY, script, timeout_seconds=30, job_id='a'*32)
    finally:
        manager.close()
