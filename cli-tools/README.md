# CLI Tools

This directory contains quite a few Python files, which are supposed to be run as native CLI tools in the terminal and do some useful stuff.

**[Some tools described in more detail.](#tool-details)**

<br>
<br>

## Run the files as native CLI tools

To run these Python scripts as native CLI tools in your terminal, follow these steps.

<br>

### Prerequisites

> [!IMPORTANT]<br>
> Before you begin, ensure you have Python installed and **added to your system's PATH**.<br>
> This is crucial for the CLI tools to be recognized and executed.
>
> *   **Windows:** make sure to check the box `Add Python to PATH` and if possible `Install for all users` during the installation of Python.<br>
>     Verify Python is in your PATH by typing `python --version` or `py --version` in your terminal.
>
> *   **macOS and Linux:** Python is often pre-installed, but you should verify it's in your PATH by typing `python3 --version` in your terminal.

<br>

### Step 1: Download the Files 📂

Download <a title="Click to download" href="https://git-link.vercel.app/api/download?url=https://github.com/xulbux/python/tree/main/cli-tools">**all files in this directory**</a>, including all Python scripts, shared modules, and the `requirements.txt` file.<br>
Place them all in a single, permanent directory on your computer. We'll call this your *cli-tools-directory*.

<br>

<span id="install-deps" />

### Step 2: Install Dependencies 📦

Before the scripts can run, you need to install their required Python packages.

1.  Open your terminal.
2.  Navigate to your *cli-tools-directory* using the `cd` command:

    ```bash
    cd "/path/to/your/cli-tools-directory"
    ```

3.  Install the dependencies using pip:

    #### Windows:

    ```powershell
    py -m pip install --upgrade -r "requirements.txt"
    ```

    #### macOS and Linux:

    Create a dedicated `.venv` virtual environment inside your *cli-tools-directory* and install the dependencies into it (Debian/Ubuntu may require `sudo apt install python3-venv` first):

    ```bash
    python3 -m venv .venv
    .venv/bin/pip install --upgrade -r "requirements.txt"
    ```

<br>

### Step 3: Make Scripts Executable as CLI Tools ⚙️

This makes your tools available from any location in your terminal.

#### Windows:

*   **Add the *cli-tools-directory* to your system's `Path` environment variable:**
    1.  Open the Start Menu, search for “Environment Variables”, and select `Edit the system environment variables`.
    2.  In the `System Properties` window, click `Environment Variables…`.
    3.  Under the `System variables` section, find and select the `Path` variable, then click `Edit…`.
    4.  Click `New` and paste in the absolute path to your *cli-tools-directory*.
    5.  Click `OK` to close all dialogs.
*   **Assure correct file associations for `.py` and `.pyw` files:**
    1.  In the File Explorer, right-click on any `.py` file and select `Open with` > `Choose another app`.
    2.  Scroll all the way down and click `Choose an app on your PC`.
    3.  Navigate to your Python installation directory (e.g., `C:\Program Files\Python\`), select `python.exe`, and click `Open`.
    4.  Now click on `Always` to set Python as the default app for `.py` files.
    5.  Lastly, repeat the same steps for a <code>.py**w**</code> file, but select <code>python**w**.exe</code> instead of `python.exe` under step 3.


#### macOS and Linux:

Add a small loader function to your shell's configuration file.<br>
It scans your *cli-tools-directory* and automatically creates an alias for each `.py` file, allowing you to run each tool directly by its name:

1.  Open your shell configuration file (e.g., `nano ~/.zshrc`):
    *   **Bash** (Linux default)**:** edit `~/.bashrc`
    *   **Zsh** (macOS default)**:** edit `~/.zshrc`
    *   **Fish:** edit `~/.config/fish/config.fish`

2.  Add the loader function for your shell to the end of the file:
    > [!TIP]<br>
    > Adjust `py_tool_dir` to your actual *cli-tools-directory* path (shown relative to `$HOME`).<br>
    > `py_venv_bin` is automatically derived from it to point to your `.venv` Python binary.

    *   **Bash (`~/.bashrc`):**

        ```bash
        # Load Python CLI tool aliases:
        _load_cli_tools() {
          local py_tool_dir="$HOME/path/to/cli-tools"
          local py_venv_bin="$py_tool_dir/.venv/bin/python"

          if [[ -d "$py_tool_dir" ]]; then
            for script in "$py_tool_dir"/*.py; do
              [[ -f "$script" ]] || continue
              local base="${script##*/}"
              local cmd_name="${base%.py}"
              alias "$cmd_name"="\"$py_venv_bin\" \"$script\""
            done
          fi
        }
        _load_cli_tools
        unset -f _load_cli_tools
        ```

    *   **Zsh (`~/.zshrc`):**

        ```zsh
        # Load Python CLI tool aliases:
        () {
          local py_tool_dir="$HOME/path/to/cli-tools"
          local py_venv_bin="$py_tool_dir/.venv/bin/python"

          if [[ -d "$py_tool_dir" ]]; then
            for script in "$py_tool_dir"/*.py(N); do
              local cmd_name=${${script##*/}%.py}
              alias "$cmd_name"="\"$py_venv_bin\" \"$script\""
            done
          fi
        }
        ```

    *   **Fish (`~/.config/fish/config.fish`):**

        ```fish
        # Load Python CLI tool aliases:
        set -l py_tool_dir "$HOME/path/to/cli-tools"
        set -l py_venv_bin "$py_tool_dir/.venv/bin/python"

        if test -d "$py_tool_dir"
          for script in "$py_tool_dir"/*.py
            test -f "$script"; or continue
            set -l cmd_name (string replace -r '\.py$' '' (basename "$script"))
            alias "$cmd_name" "\"$py_venv_bin\" \"$script\""
          end
        end
        ```

3.  Save the file, and then apply the changes by restarting the terminal (or by running `source ~/.zshrc`, or `source ~/.bashrc`).

<br>

### Step 4: Restart your Terminal ✅

Close and reopen your terminal.<br>
The changes are now active, and you can run the files by typing their names (e.g., [`x-tools`](#x-tools)).

<br>
<br>

<span id="tool-details" />

## Some Tools in More Detail

Run any tool with `-h` or `--help` to see its full usage information.<br>
**⇾** Each process can be canceled by pressing `Ctrl + C`.

> [!NOTE]<br>
> If any of the scripts stop working (especially after updating), ensure all dependencies are up-to-date.<br>
> Download the latest <a title="Click to download" href="https://git-link.vercel.app/api/download?url=https://github.com/xulbux/python/blob/main/cli-tools/requirements.txt">**`requirements.txt`**</a> and follow the [**Install Dependencies**](#install-deps) steps again.

<br>

### `x-tools`

This tool outputs a compact summary of all custom Python CLI tools in your *cli-tools-directory* with their descriptions and arguments/options.<br>
It also allows you to easily check for and apply updates for all managed tools in the directory when run with `-u` or `--update`.

#### How the Update System Works

The update system is designed to keep managed tools up-to-date while protecting your custom files:

*   **Managed Tools:** Only files with the comment `# x-tools:file[update]` at the top (after the shebang) are checked for updates.<br>
    These tools can be automatically updated or deleted if they're removed from the repository.

*   **User Tools:** Files **without** the `# x-tools:file[update]` marker are considered user-created and will **never** be modified or deleted by the update system, keeping your custom tools safe.

*   **Update Detection:** The system checks multiple GitHub repository URLs (configurable in the script), merges all available tools, and detects three types of changes:
    -   **New tools** – Available in the repository but not locally.
    -   **Updated tools** – Local managed tools with content changes.
    -   **Deleted tools** – Local managed tools no longer in any repository.

This approach allows you to safely add your tools to the directory while still benefiting from automatic updates.
