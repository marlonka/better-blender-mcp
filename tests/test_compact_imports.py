import subprocess
import sys


def test_compact_server_does_not_import_legacy_telemetry_or_integrations():
    subprocess.run([sys.executable, '-c', '''import sys
import blender_mcp.compact_server
assert 'blender_mcp.server' not in sys.modules
assert 'blender_mcp.telemetry' not in sys.modules
'''], check=True, timeout=10)
