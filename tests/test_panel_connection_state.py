"""A saved scene's connection flag must not override the active socket server."""
import ast
from types import SimpleNamespace

import pytest

from conftest import ROOT_ADDON


class Layout:
    def __init__(self):
        self.labels = []
        self.operators = []

    def box(self, **kwargs):
        return self

    column = box

    def label(self, *, text, **kwargs):
        self.labels.append(text)

    def operator(self, name, **kwargs):
        self.operators.append(name)

    def prop(self, *args, **kwargs):
        pass

    def separator(self):
        pass


@pytest.mark.parametrize('server,stored_flag,expected_label,expected_operator', [
    (SimpleNamespace(running=True, port=9876), False, 'Connected on port 9876', 'blendermcp.stop_server'),
    (SimpleNamespace(running=False, port=9876), True, 'Not connected', 'blendermcp.start_server'),
    (None, True, 'Not connected', 'blendermcp.start_server'),
])
def test_panel_uses_actual_server_after_loading_scene(server, stored_flag, expected_label, expected_operator):
    tree = ast.parse(ROOT_ADDON.read_text(encoding='utf-8'))
    panel = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'BLENDERMCP_PT_Panel')
    draw = next(n for n in panel.body if isinstance(n, ast.FunctionDef) and n.name == 'draw')
    namespace = {'bpy': SimpleNamespace(types=SimpleNamespace(blendermcp_server=server)),
                 'get_blendermcp_addon_preferences': lambda context: None}
    exec(compile(ast.Module(body=[draw], type_ignores=[]), '<panel>', 'exec'), namespace)
    layout = Layout()
    instance = SimpleNamespace(layout=layout, _integration_header=lambda *args: None)
    context = SimpleNamespace(scene=SimpleNamespace(blendermcp_server_running=stored_flag, blendermcp_port=9999))
    namespace['draw'](instance, context)
    assert layout.labels[0] == expected_label
    assert layout.operators == [expected_operator]
