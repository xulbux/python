# CLI Tools

This directory contains quite a few Python files, which are supposed<br>
to be run as native CLI tools in the terminal and do some useful stuff.

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
> *   **Windows:** make sure to check the box `Add Python to PATH`<br>
>     and if possible `Install for all users` during the installation of Python.<br>
>     Verify Python is in your PATH by typing `python --version` or `py --version` in your terminal.
>
> *   **macOS and Linux:** Python is often pre-installed, but you should verify<br>
>     it's in your PATH by typing `python3 --version` in your terminal.

<br>

### Step 1: Download the Files

Download the Python files you want to use, along with the <a title="Click to download" href="https://git-link.vercel.app/api/download?url=https://github.com/xulbux/python/blob/main/cli-tools/requirements.txt">**`requirements.txt`**</a> file.<br>
Place them all in a single, permanent directory on your computer. We'll call this your *cli-tools-directory*.

> [!IMPORTANT]<br>
> The way you prepare the files depends on your operating system:
>
> *   **Windows:** You can leave the `.py` or `.pyw` extension on the files.<br>
>     As long as both `PY` and `PYW` are in your system's `PATHEXT` environment variable<br>
>     (*which is the default*), you can run the tools without typing `.py`.
>
> *   **macOS and Linux:** You **must remove the `.py` or `.pyw` extension** from the script files.<br>
>     For example, rename `x-tools.py` to `x-tools`.<br>
>     This allows the operating system to execute them as native CLI tools.

<br>

<span id="install-deps" />

### Step 2: Install Dependencies

Before the scripts can run, you need to install their required Python packages. 📦

1.  Open your terminal.
2.  Navigate to your *cli-tools-directory* using the `cd` command.

    ```bash
    cd "/path/to/your/cli-tools-directory"
    ```

3.  Install the dependencies using pip:

    ```bash
    py -m pip install --upgrade -r "requirements.txt"
    ```

<br>

### Step 3: Make Scripts Executable as CLI Tools

This makes your tools available from any location in your terminal. ⚙️

#### Windows:

*   **Add the *cli-tools-directory* to your system's `Path` environment variable:**
    1.  Open the Start Menu, search for "Environment Variables", and select `Edit the system environment variables`.
    2.  In the `System Properties` window, click `Environment Variables…`.
    3.  Under the `System variables` section, find and select the `Path` variable, then click `Edit…`.
    4.  Click `New` and paste in the absolute path to your *cli-tools-directory*.
    5.  Click `OK` to close all dialogs.
*   **Assure correct file associations for `.py` and `.pyw` files:**
    1.  In the File Explorer, right-click on any `.py` file and select `Open with` > `Choose another app`.
    2.  Scroll all the way down and click `Choose an app on your PC`.
    3.  Navigate to your Python installation directory (*e.g.,* `C:\Program Files\Python\`), select `python.exe`, and click `Open`.
    4.  Now click on `Always` to set Python as the default app for `.py` files.
    5.  Lastly, repeat the same steps for a <code>.py**w**</code> file, but select <code>python**w**.exe</code> instead of `python.exe` under step 3.


#### macOS and Linux:

*   **Add a shebang line:** Make sure the very first line of every script file is `#!/usr/bin/env python3`.<br>
    (*Note: This is already done for you in all the repository's files.*)
*   **Make the files executable:** Open your terminal and run the following command, replacing the path with your own:

    ```bash
    chmod +x "/path/to/your/cli-tools-directory/*"
    ```

*   **Add the directory to your terminal's PATH:**
    1.  For modern **macOS** (*and Linux with Zsh*), edit `~/.zshrc`.
    2.  For most **Linux** distributions, edit `~/.bashrc`.
    3.  Open the file (*e.g.,* `nano ~/.zshrc`) and add this line to the end:

        ```bash
        export PATH="$PATH:/path/to/your/cli-tools-directory"
        ```

    4.  Save the file, and then apply the changes by running `source ~/.zshrc` (*or the file you edited*).

<br>

### Step 4: Restart your Terminal

Close and reopen your terminal.<br>
The changes are now active, and you can run the files by typing their names (*e.g.,* [`x-tools`](#x-tools)). ✅

<br>
<br>

<span id="tool-details" />

## Some Tools in More Detail

Run any tool with `-h` or `--help` to see its full usage information.<br>
**⇾** Each process can be canceled by pressing `Ctrl + C`.

> [!NOTE]<br>
> If any of the scripts stop working (*especially after updating*), ensure all dependencies are up-to-date.<br>
> Download the latest <a title="Click to download" href="https://git-link.vercel.app/api/download?url=https://github.com/xulbux/python/blob/main/cli-tools/requirements.txt">**`requirements.txt`**</a> and follow the [**Install Dependencies**](#install-deps) steps again.

<br>

### `x-tools`

This tool outputs a list of all custom Python CLI tools in the current directory,<br>
with a short description (*if provided*) and their params (*if found*).

⇾ To adjust some update-checking-options, you can edit the `CONFIG` variable, inside the script file.

#### How the Update System Works

The update system is designed to keep managed tools up-to-date while protecting your custom files:

*   **Managed Tools:** Only files with the comment `# x-tools:file[update]` at the top (*after the shebang*) are checked for updates.<br>
    These tools can be automatically updated or deleted if they're removed from the repository.

*   **User Tools:** Files **without** the `# x-tools:file[update]` marker are considered user-created and<br>
    will **never** be modified or deleted by the update system, keeping your own custom tools safe.

*   **Update Detection:** The system checks multiple GitHub repository URLs (*configurable in the script*),<br>
    merges all available tools, and detects three types of changes:
    -   **New tools** – Available in the repository but not locally.
    -   **Updated tools** – Local managed tools with content changes.
    -   **Deleted tools** – Local managed tools no longer in any repository.

This approach allows you to safely add your own tools to the directory while still benefiting from automatic updates.
