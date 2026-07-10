# CST 2026 Automation and Scripting Audit

Source audited: `D:\CST2026\CST Studio Suite 2026\Online Help`

Date: 2026-07-05

## Scope and Search Method

The CST Online Help folder contains 20,445 files, including 7,872 `.htm` files and 233 `.html` files. The audit used parallel keyword searches over the whole Help tree, then manually inspected the pages that define official interfaces. The companion script `scripts/cst_help_automation_scan.py` can rerun the page-level search against this or a newer CST Help directory.

Primary keyword families:

- `Automation and Scripting`, `scripting`, `automation`
- `VBA`, `Visual Basic`, `macro`, `RunMacro`, `RunScript`, `AddToHistory`
- `Python`, `cst.interface`, `DesignEnvironment`, `execute_vba_code`, `get_current_project`
- `Command Line Options`, `.bas`, `Model.run`, `batch mode`
- `OLE`, `COM`, `CreateObject`, `CSTStudio.Application`

Noise was high in MathJax/static assets, so the final interpretation relies on HTML Help pages and official Help indexes, not raw JavaScript resource hits.

Navigation/index coverage notes:

- `whxdata\whtoc_xml.js` places `mergedProjects/VBA_3D`, `mergedProjects/VBA_DES`, and `mergedProjects/Python` under `Automation and Scripting`.
- `whcshdata.js` registers `mergedProjects/VBA_3D`, `mergedProjects/VBA_DES`, and `mergedProjects/Python` as remote projects.
- `mergedProjects\VBA_3D\whxdata\topictable_0_xml.js` and `mergedProjects\VBA_DES\whxdata\topictable_0_xml.js` are important even where TOC files are sparse; they contain the actual VBA object topic inventory.
- `user_scipts.htm` is misspelled in the Help tree. Searches for only `scripts` can miss this page.

## Bottom Line

CST 2026 has several official automation paths relevant to running VBA macros without manual CST interaction:

1. **Command line batch mode can execute `.bas` BASIC/VBA files.** The Command Line Options page says `.bas` files execute the BASIC file, with a CST module flag such as `-m`, `-s`, `-t`, or `-c`.
2. **CST is an OLE automation server.** The registered COM application is `CSTStudio.Application`; CST 2026 can be requested as `CSTStudio.Application.2026`.
3. **VBA project objects expose `RunMacro` and `RunScript`.** Both 3D Simulation VBA and Design Studio VBA document `RunMacro(string macroname)` and `RunScript(string scriptname)`.
4. **The official Python interface can open/connect projects and execute VBA snippets in some contexts.** `cst.interface.DesignEnvironment` opens/connects CST projects; `Model3D.add_to_history(header, vba_code)` executes VBA code as a history block; `Schematic.execute_vba_code(vba_code)` executes a schematic VBA snippet.
5. **The Help does not show a direct Python method named `run_macro` or `run_script` on `cst.interface.Project` / `Model3D`.** For Python-driven workflows, the officially documented bridge is either executing VBA text through `add_to_history` / `execute_vba_code`, or using the VBA Project Object methods from inside such VBA text. This should be live-CST validated before building a production wrapper.
6. **GUI macro import exists, but an import API was not found in the inspected Help pages.** `Import VBA Macro` is documented as a dialog that copies a macro from a previously chosen project into the current project.

## Official Interface Inventory

### 1. Command Line Batch Mode

Source: `D:\CST2026\CST Studio Suite 2026\Online Help\advanced\commandlineoptions.htm`

Relevant findings:

- CST can run in batch mode.
- Windows syntax is documented as:

```text
"<Installation Path>\CST DESIGN ENVIRONMENT.exe" <options> "<full path of cst file>"
```

- Module flags include:
  - `-m`: starts CST Microwave Studio.
  - `-s`: starts CST EM Studio.
  - `-t`: starts CST Particle Studio.
  - `-mp`: starts CST Mphysics Studio.
  - `-c`: starts CST Design Studio.
  - `-cs`: starts CST Cable Studio.
  - `-pcbs`: starts CST PCB Studio.
  - `-hide`: starts in the background without interaction possible.
- File extension behavior:
  - `.bas`: executes the BASIC file; `-m`, `-s`, `-t`, or `-c` must be specified.
  - `.cst`: loads a CST project; `-m`, `-s`, `-t`, `-mp`, or `-c` must be specified.
  - `.des`: loads a CST Design Studio project; `-c` must be specified.
- Calculation flags include:
  - `-as`: starts the active solver for the saved project.
  - `-p`: starts a parameter sweep with the active solver.
  - `-o`: starts the optimizer with the active solver.
  - `-b`: executes `Model.run` located in the project `Model/3D/` folder; valid for `-m`, `-s`, or `-t`.
- The page explicitly states that other settings can be handled by executing an appropriate Visual Basic file and that each module can be controlled through Visual Basic commands.

Implication for this repository:

- A no-manual route exists for standalone `.bas` scripts:

```powershell
& "D:\CST2026\CST Studio Suite 2026\CST DESIGN ENVIRONMENT.exe" -m -hide "C:\path\to\macro.bas"
```

- For project-bound automation, do not assume the command line accepts both a `.cst` and a `.bas` as separate positional inputs unless live-tested. Safer official alternatives are:
  - write the `.bas` so it opens the project through the Application Object; or
  - use project-local `Model/3D/Model.run` with `-b`; or
  - use Python/COM to open the project and then execute VBA.

### 2. OLE / COM Application Object

Source: `D:\CST2026\CST Studio Suite 2026\Online Help\advanced\vbaapplicationobject.htm`

Official object:

```vb
Set app = CreateObject("CSTStudio.Application")
Set app = CreateObject("CSTStudio.Application.2026")
```

Documented capabilities:

- `NewMWS`, `NewEMS`, `NewPS`, `NewMPS`, `NewCS`, `NewPCBS`, `NewDS`: create new projects.
- `OpenFile`: opens a project.
- `Active3D`: access the current CST Microwave Studio / EM Studio / Particle Studio / Mphysics Studio / Cable Studio project.
- `ActiveDS`: access the current CST Design Studio project.
- quiet mode suppresses message boxes, but dialogs requiring user input cannot be suppressed.
- `ProtectProject`, `GetFileMainVersion`, `GetFilePatchVersion`, `Quit`.

Implication:

- If Python `cst.interface` does not expose a direct macro runner for the exact needed case, COM automation is an official CST entry point on Windows. The wrapper must use only documented COM/VBA methods such as `OpenFile`, `Active3D` / `ActiveDS`, `RunScript`, `RunMacro`, and `Quit`.

### 3. VBA Project Object: 3D Simulation

Source: `D:\CST2026\CST Studio Suite 2026\Online Help\mergedProjects\VBA_3D\common_vbaapp\common_vbaappapplication_object.htm`

High-value methods:

- `AddToHistory(caption, contents)`: adds a history entry and executes the VBA contents.
- `RunSolver()`: starts the currently active solver.
- `GetMacroPath`, `GetMacroPathFromIndex`, `GetNumberOfMacroPaths`: inspect global macro directories.
- `RunAndWait(command)`: executes an external command and waits.
- `RunMacro(macroname)`: starts execution of a macro.
- `RunScript(scriptname)`: reads script input of a file.

Implication:

- For an already-open 3D project COM/VBA handle, `RunScript("C:\path\macro.bas")` is the most direct documented route to run a script file.
- `RunMacro("name")` is appropriate when the macro is already project-local or global and addressable by CST's macro name/path convention.
- `AddToHistory` is useful for model-changing VBA snippets that should be replayable. It is not the same as a control macro; it records a history block.

### 4. VBA Project Object: Design Studio

Source: `D:\CST2026\CST Studio Suite 2026\Online Help\mergedProjects\VBA_DES\special_vbacommands\projectobject.htm`

Relevant methods mirror the 3D side:

- `GetMacroPath`, `GetMacroPathFromIndex`
- `RunAndWait(command)`
- `RunMacro(macroname)`
- `RunScript(scriptname)`

Design Studio also has an `Execute Macro` dialog page:

`D:\CST2026\CST Studio Suite 2026\Online Help\mergedProjects\DES\macro\common_macro_execute_macro.htm`

That page confirms CST distinguishes project macros and global macros and executes the selected macro from the available macro list.

### 5. Python `cst.interface`

Source: `D:\CST2026\CST Studio Suite 2026\Online Help\Python\source\cst.interface.html`

Additional tutorial sources:

- `D:\CST2026\CST Studio Suite 2026\Online Help\PythonTutorial\3d_simulation_getting_started.html`
- `D:\CST2026\CST Studio Suite 2026\Online Help\PythonTutorial\3d_simulation_structure_modeling.html`
- `D:\CST2026\CST Studio Suite 2026\Online Help\PythonTutorial\3d_simulation_simulation_setup.html`
- `D:\CST2026\CST Studio Suite 2026\Online Help\PythonTutorial\3d_simulation_results.html`

Documented capabilities:

- `cst.interface.DesignEnvironment` controls CST Studio Suite.
- `DesignEnvironment.new(options=None, ...)` opens and connects to a new Design Environment. Command line options may be passed as a list.
- `DesignEnvironment.connect(pid)` connects to an existing Design Environment by PID.
- `DesignEnvironment.connect(tcp_address)` connects by TCP address.
- `DesignEnvironment.connect_to_any()` and `connect_to_any_or_new()` attach to existing/new CST sessions.
- `DesignEnvironment.open_project(path)` opens a `.cst` project and returns a `Project`.
- `Project.model3d` gives access to `Model3D`.
- `Project.schematic` gives access to `Schematic`.
- `Model3D.add_to_history(header, vba_code, timeout=None)` creates a modeler history block and executes the VBA code.
- `Schematic.execute_vba_code(vba_code, timeout=None)` executes a VBA code snippet.
- `Model3D.run_solver()`, `start_solver()`, `is_solver_running()`, `abort_solver()`, etc. control solver execution.
- `running_design_environments()` returns PIDs of currently running Design Environments.
- The structure-modeling tutorial uses generated VBA strings plus `prj.model3d.add_to_history(...)` for geometry and setup commands.

Important limitation:

- The inspected `cst.interface` page does not document `Project.run_macro`, `Project.run_script`, `Model3D.run_macro`, or `Model3D.execute_vba_code`.
- The tutorials use `from cst.interface import get_current_project`, but the inspected API reference page did not list it as a documented function entry. Treat it as tutorial-supported and verify against the installed `python_cst_libraries` before wrapping it.
- For 3D projects, the documented Python-to-VBA execution method is `Model3D.add_to_history`, which has a history side effect.
- For schematic/Design Studio contexts, `Schematic.execute_vba_code` is a direct snippet executor.

Candidate Python bridge to live-test:

```python
import cst.interface

de = cst.interface.DesignEnvironment.connect_to_any_or_new()
prj = de.open_project(r"C:\path\to\project.cst")

# 3D modeler route: documented to execute VBA while adding a history block.
prj.model3d.add_to_history(
    "run external VBA script",
    'RunScript "C:\\path\\to\\macro.bas"',
)

# Schematic route: documented direct VBA snippet execution.
prj.schematic.execute_vba_code('RunScript "C:\\path\\to\\macro.bas"')
```

This is an inference from two official facts: Python can execute VBA snippets in these ways, and the VBA Project Object has `RunScript`. Validate on a disposable CST project before using it in WF2/WF3.

### 6. Python Menu and Generic Commands

Sources:

- `D:\CST2026\CST Studio Suite 2026\Online Help\PythonTutorial\3d_simulation_getting_started.html`
- `D:\CST2026\CST Studio Suite 2026\Online Help\PythonTutorial\custom_python.html`
- `D:\CST2026\CST Studio Suite 2026\Online Help\user_scipts.htm`

Findings:

- Python scripts under a configured CST library path at `Python/scripts/` appear under `Home: Macros -> Python -> Run Script` after `Update Menu`.
- `user_scipts.htm` states the same Python user-script convention, despite the filename typo.
- Scripts executed this way use CST's integrated Python interpreter by default.
- `get_current_project()` uses `--cst-pid` and `--prj` options to retrieve the current project handle.
- Generic Command JSON files under `<library-path>/Commands/` can add custom menu commands.
- Command JSON supports fields such as `name`, `program`, `args`, `cwd`, `console`, `restrict_to`, `subcommands`.
- Interpolation variables include `${CST_STUDIO_PID}`, `${CST_ACTIVE_PROJECT}`, `${CST_INSTALL_PATH}`, `${CST_INSTALL_PATH_AMD64}`, `${CST_DEFAULT_LOCAL_LIBRARY_PATH}`, and `${CST_COMMAND_DIR}`.

Implication:

- This is useful for distributing team tools inside CST's GUI, but it is not by itself a headless workflow trigger. For unattended optimisation, prefer command line / Python `cst.interface` / COM.

### 7. VBA Macro Concepts and Storage

Sources:

- `D:\CST2026\CST Studio Suite 2026\Online Help\vba\vba_macro_language_overview.htm`
- `D:\CST2026\CST Studio Suite 2026\Online Help\mergedProjects\3D\common_overview\common_overview_vba.htm`
- `D:\CST2026\CST Studio Suite 2026\Online Help\mergedProjects\3D\common_macro\common_macro_store_macro.htm`
- `D:\CST2026\CST Studio Suite 2026\Online Help\mergedProjects\3D\common_macro\common_macro_import_macro.htm`
- `D:\CST2026\CST Studio Suite 2026\Online Help\mergedProjects\3D\common_macro\common_macro_edit_macro.htm`
- `D:\CST2026\CST Studio Suite 2026\Online Help\mergedProjects\3D\common_macro\common_macro_projectmacros.htm`
- `D:\CST2026\CST Studio Suite 2026\Online Help\mergedProjects\3D\common_macro\common_macro_globalmacro.htm`
- `D:\CST2026\CST Studio Suite 2026\Online Help\mergedProjects\3D\common_macro\common_macro_history_list.htm`
- `D:\CST2026\CST Studio Suite 2026\Online Help\mergedProjects\3D\common_preloadedmacro\common_preloadedmacro_preloaded_macros_overview.htm`
- `D:\CST2026\CST Studio Suite 2026\Online Help\mergedProjects\3D\common_preloadedmacro\common_preloadedmacro_wizard_compare_multiple_runs.htm`

Findings:

- CST tools can be controlled from a VBA script; the built-in interpreter is almost fully Visual Basic for Applications compatible.
- The VBA language is intended for structure libraries and common task automation.
- CST also has OLE automation integration with external Windows applications.
- Each VBA program must have at least `Sub Main`, which is automatically called when the program starts.
- Macros can be project-local or global.
- Global macros are stored in a macros folder in the installation directory and are automatically available in all projects.
- Project/local macros are stored with the active project.
- Macro names can use a submenu structure, documented as `<submenu/name>`.
- Control macros are typically used for automatic calculation sequences and are not stored in the history list when executed.
- Structure macros are model-building macros, identified by `.mcs`, and their contents are appended to the history list when run from the Macros menu.
- The `Import VBA Macro` dialog copies a selected macro from a previously chosen project into the current project. The Help documents the GUI behavior, not a separate import API.
- The `Edit / Move / Delete Macro` dialog can list project/global macros; `Edit` opens the VBA Interpreter/Editor and loads the selected file.
- The History List records important actions as VBA commands and can convert selected history commands into a new project macro.
- CST installs preloaded global macros for common tasks, including construction, report/graphics, EMC/farfield, 1D result processing, and filter-analysis utilities.
- One preloaded macro page documents additional user-defined post-processing `.BAS` files under `GLOBAL_Library_PATH\Macros\MWS\VBA_userdefined`, with filename patterns such as `0D-Result_*.BAS` and `1D-Result_*.BAS`.

Implication:

- If the new workflow needs reproducible geometry mutation, prefer explicit `AddToHistory` blocks or structure macro behavior.
- If the new workflow needs one-off calculations, post-processing, or orchestration, prefer control macros / `RunScript` to avoid polluting the model history.

### 8. Python Results Access

Source: `D:\CST2026\CST Studio Suite 2026\Online Help\Python\source\cst.results.html`

Findings:

- `cst.results.ProjectFile(filepath, allow_interactive=False)` opens CST project files for results access.
- `get_3d()` and `get_schematic()` access result submodules.
- Result access supports 0D/1D result items and 2D colormap results.
- `allow_interactive=True` can access a project that is simultaneously open in CST, but data is valid only after CST has saved; unsaved solver/model changes can make retrieved data outdated or ill-formed.

Implication:

- Keep macro execution/control in `cst.interface` or COM.
- Keep result extraction in `cst.results`, with explicit save points before reading.

### 9. Adjacent Batch Interfaces

The main CST Studio Suite automation findings above are the relevant ones for WF2/WF3. The full Help scan also found IdEM / Opera batch and scripting pages outside the `Automation and Scripting` tree, for example `IdEM\idem\idem_mpbatch.htm` and DES IdEM batch-mode help. These are adjacent tools rather than the core CST Microwave Studio VBA/Python path, so they are not recommended for the HOM antenna workflow unless that workflow later invokes IdEM-specific processing.

## Recommended Implementation Path for the New Workflow

### Preferred route: Python runner opens CST, then delegates macro execution officially

1. Use `cst.interface.DesignEnvironment.connect_to_any_or_new()` or `DesignEnvironment.new(options=[...])`.
2. Open the target project with `de.open_project(project_path)`.
3. For small model-changing snippets, call `prj.model3d.add_to_history(header, vba_code)`.
4. For external `.bas` scripts, live-test `RunScript` through the documented VBA layer:
   - 3D: `prj.model3d.add_to_history("run script", 'RunScript "C:\\path\\script.bas"')`
   - Schematic: `prj.schematic.execute_vba_code('RunScript "C:\\path\\script.bas"')`
5. For project/global macros, live-test `RunMacro("macro_name")` the same way.
6. Save the project before reading results with `cst.results`.

### Alternative route: COM automation wrapper

Use Windows COM with official `CSTStudio.Application.2026`:

```vb
Set app = CreateObject("CSTStudio.Application.2026")
Set mws = app.OpenFile("C:\path\project.cst")
mws.RunScript "C:\path\macro.bas"
mws.Save
app.Quit
```

This is closest to CST's VBA/OLE documentation and may be the cleanest way to run control macros without adding model history blocks. If implemented in Python, use a COM library only as a transport to these documented CST methods.

### Batch route

Use command line `.bas` execution when the macro can own opening/closing the project:

```powershell
& "D:\CST2026\CST Studio Suite 2026\CST DESIGN ENVIRONMENT.exe" -m -hide "C:\path\driver.bas"
```

Inside `driver.bas`, use `CreateObject("CSTStudio.Application.2026")` or CST global objects according to context, then open the project and run operations.

For project-local batch hooks, use `Model/3D/Model.run` plus `-b` where appropriate.

## Open Questions Requiring Live CST Validation

- Whether `RunScript("absolute\path\script.bas")` works from `Model3D.add_to_history` in all relevant 3D modules, and whether it creates unwanted history side effects.
- Exact macro naming accepted by `RunMacro`, especially submenu names and global macro paths.
- Whether command line invocation can combine a `.cst` project path and a `.bas` script in one process. The inspected Help page documents extension behavior, but not a combined example.
- Whether `-hide` is safe for all WF2/HOM antenna macro operations; dialogs requiring user input are not suppressible according to the Application Object page.
- Where this CST installation stores user/global macro folders in practice. Use `GetMacroPath` / `GetMacroPathFromIndex` from a live CST session to avoid guessing.
- Whether the installed `cst.interface` package exports `get_current_project` even though the API page does not list it. The tutorial uses it for menu-launched Python scripts.

## Pages Worth Keeping Pinned

- `D:\CST2026\CST Studio Suite 2026\Online Help\advanced\commandlineoptions.htm`
- `D:\CST2026\CST Studio Suite 2026\Online Help\advanced\vbaapplicationobject.htm`
- `D:\CST2026\CST Studio Suite 2026\Online Help\mergedProjects\VBA_3D\common_vbaapp\common_vbaappapplication_object.htm`
- `D:\CST2026\CST Studio Suite 2026\Online Help\mergedProjects\VBA_DES\special_vbacommands\projectobject.htm`
- `D:\CST2026\CST Studio Suite 2026\Online Help\Python\source\cst.interface.html`
- `D:\CST2026\CST Studio Suite 2026\Online Help\Python\source\cst.results.html`
- `D:\CST2026\CST Studio Suite 2026\Online Help\PythonTutorial\custom_python.html`
- `D:\CST2026\CST Studio Suite 2026\Online Help\PythonTutorial\3d_simulation_structure_modeling.html`
- `D:\CST2026\CST Studio Suite 2026\Online Help\user_scipts.htm`
- `D:\CST2026\CST Studio Suite 2026\Online Help\vba\vba_macro_language_overview.htm`
- `D:\CST2026\CST Studio Suite 2026\Online Help\mergedProjects\3D\common_overview\common_overview_vba.htm`
- `D:\CST2026\CST Studio Suite 2026\Online Help\mergedProjects\3D\common_preloadedmacro\common_preloadedmacro_preloaded_macros_overview.htm`
