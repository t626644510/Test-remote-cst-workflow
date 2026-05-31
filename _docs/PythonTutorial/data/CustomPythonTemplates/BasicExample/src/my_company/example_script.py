import math
import numpy as np

import cst.results
from cst.interface import get_current_project


def main():
    prj = get_current_project()
    de = prj.design_environment

    with de.quiet_mode_enabled():
        hf_prj = de.new_mws()
        hf_prj.model3d.RunMacro(r"Construct/Demo Examples/Dipole Antenna")
        hf_prj.model3d.run_solver()

        project_file = cst.results.ProjectFile(hf_prj.filename(), allow_interactive=True)
        resmod_3d = project_file.get_3d()
        resitem_s11 = resmod_3d.get_result_item("1D Results\\S-Parameters\\S1,1")

        resitem_s11.get_xdata()
        np.array(resitem_s11.get_xdata())
        f = np.array(resitem_s11.get_xdata())
        s11 = np.array(resitem_s11.get_ydata())

        s11_min_ind = np.argmin(np.abs(s11))
        fmax_rad = f[s11_min_ind]
        s11_min_db = 20 * math.log10(np.abs(s11[s11_min_ind]))

        hf_prj.model3d.ReportInformation(
            f"From Python: Maximum radiation occurs at f={float(fmax_rad)}GHz with S11={s11_min_db}dB"
        )


if __name__ == "__main__":
    main()
