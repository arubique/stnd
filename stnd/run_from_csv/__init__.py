# Import only what's needed for the module interface
# to avoid warning: "'stnd.run_from_csv.__main__' found in sys.modules after import of package 'stnd.run_from_csv', but prior to execution of 'stnd.run_from_csv.__main__'; this may result in unpredictable behaviour"
def main():
    from .__main__ import main as _main
    return _main()

def make_final_cmd_slurm(*args, **kwargs):
    from .__main__ import make_final_cmd_slurm as _make_final_cmd_slurm
    return _make_final_cmd_slurm(*args, **kwargs)

def extract_from_csv_row_by_prefix(*args, **kwargs):
    from .__main__ import extract_from_csv_row_by_prefix as _extract_from_csv_row_by_prefix
    return _extract_from_csv_row_by_prefix(*args, **kwargs)
