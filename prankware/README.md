# Prankware

This repository contains **harmless** prank scripts (*also as [executables](./exe)*), that do all sorts of annoying things.

> [!CAUTION]<br>
> These scripts lead to actions on your PC that you may not want.
> However, it is important to note that **none of these scripts will cause any damage to your PC**.


## add_shutdown_script_to_startup_directory_and_shutdown_pc | [view script](./scripts/add_shutdown_script_to_startup_directory_and_shutdown_pc.py)

This script/EXE will first create a second file `notSUS` in the user's startup directory (`C:\Users\%USERNAME%\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup`).<br>
Subsequently, it will start PC shutdown in `{time}` minutes display a message: `PC is shutting down in {time} minutes.`<br>
The `notSUS` file does the same thing (shutdown PC after `{time}` minutes and display message).<br>
Per default, the **`{time}` before shutdown is set to `5 minutes`**, so there's enough time to delete the `notSUS` file from the startup directory, before shutdown happens again.

### [Download](https://github.com/xulbux/python/raw/refs/heads/main/prankware/exe/add_shutdown_script_to_startup_directory_and_shutdown_pc.exe)

> [!NOTE]<br>
> This script/EXE works on all OSes.


## make_lots_of_colorful_random_msg_rectangles | [view script](./scripts/make_lots_of_colorful_random_msg_rectangles.pyw)

This script/EXE will simply create many colored rectangles on your screen and display a random message in each of them.<br>
There will be no way of getting rid of them, except for restarting your PC.

### [Download](https://github.com/xulbux/python/raw/refs/heads/main/prankware/exe/make_lots_of_colorful_random_msg_rectangles.exe)

> [!NOTE]<br>
> This script/EXE works on all OSes.


## not_closable_timed_maths_problems_until_correct_answer | [view script](./scripts/not_closable_timed_maths_problems_until_correct_answer.pyw)

This script/EXE will create a small window with a math problem and a timer.<br>
If you enter the wrong answer or the timer runs out, the window will renew the problem and open a second math-problem-window.<br>
Trying to close or iconify the window will not work. The only way to close a math-problem-window is by entering the correct answer in time.

### [Download](https://github.com/xulbux/python/raw/refs/heads/main/prankware/exe/not_closable_timed_maths_problems_until_correct_answer.exe)

> [!NOTE]<br>
> This script/EXE works on all OSes.


## play_annoying_sounds_on_keyboard_and_mouse | [view script](./scripts/play_annoying_sounds_on_keyboard_and_mouse.pyw)

This script/EXE will first copy itself to the user's startup directory (`C:\Users\%USERNAME%\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup`), so that it will automatically run on every system start.<br>
Subsequently, it runs in the background and plays a sound every time the user presses a keyboard key/combination or clicks a mouse button.<br>
The volume cannot be lowered lower than the set `MIN_VOLUME` (*default is 50%*) in the script. Muting will not work either.<br>
The only way to stop the script is by restarting the PC or by killing it in the task manager under the background processes (*the process is called the same as the script's/EXEs name*).

### [Download](https://github.com/xulbux/python/raw/refs/heads/main/prankware/exe/play_annoying_sounds_on_keyboard_and_mouse.exe)

> [!NOTE]<br>
> This script/EXE works **only on Windows**.


## shutdown_pc_with_virus_warning | [view script](./scripts/shutdown_pc_with_virus_warning.py)

This script/EXE will shut down your PC five seconds after being run and display a shutdown message:<br>
`WARNING: Virus detected. Starting system clean up process...`<br>
The script/EXE are named a confusing and special looking name, to make it look like a very suspicious file.

### [Download](https://github.com/xulbux/python/raw/refs/heads/main/prankware/exe/shutdown_pc_with_virus_warning.exe)

> [!NOTE]<br>
> This script/EXE works on all OSes.
