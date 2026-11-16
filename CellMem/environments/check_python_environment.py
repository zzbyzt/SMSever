"""Read-only check of the two core dependencies; never installs or fits."""
import importlib.metadata
import json
from pathlib import Path
import platform

def main():
    expected=json.loads((Path(__file__).parent/'python_core_observed.json').read_text(encoding='utf-8'))
    checks=[]
    for name,version in expected['packages'].items():
        try:actual=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:actual=None
        checks.append({'package':name,'expected':version,'observed':actual,'exact_match':actual==version})
    result={'python_version':platform.python_version(),'recorded_python_version':expected['python_version'],
            'python_exact_match':platform.python_version()==expected['python_version'],
            'packages':checks,'core_dependencies_match':all(x['exact_match'] for x in checks),
            'fit_started':False,'data_read':False}
    print(json.dumps(result,indent=2))
    return 0 if result['core_dependencies_match'] else 2

if __name__=='__main__':raise SystemExit(main())
