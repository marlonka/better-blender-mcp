"""Executed by Blender without importing the MCP package or third-party services."""
import importlib.util
import json
from pathlib import Path
import sys


def main(config_path):
    config = json.loads(Path(config_path).read_text(encoding='utf-8'))
    spec = importlib.util.spec_from_file_location('better_blender', Path(__file__).with_name('recipes.py'))
    recipes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recipes)
    sys.modules['better_blender'] = recipes
    namespace = {'__name__': '__main__'}
    if config.get('script_path'):
        original = config['script_path']
        namespace['__file__'] = original
        sys.path.insert(0, str(Path(original).parent))
        # The validated snapshot is executed even if the source file changes.
        source = Path(config['source_path']).read_text(encoding='utf-8')
        exec(compile(source, original, 'exec'), namespace)
    spec = importlib.util.spec_from_file_location('better_blender_quality', Path(__file__).with_name('quality.py'))
    quality = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(quality)
    result = quality.collect(config, namespace.get('BETTER_BLENDER_OUTPUTS', {}))
    target = Path(config['result_path'])
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(target)


if __name__ == '__main__':
    main(sys.argv[sys.argv.index('--') + 1])
