/*
 * claude_journal_launcher.c
 *
 * Tiny stable-path launcher for claude_journal.py, run by launchd
 * (com.mark.claudejournal). macOS privacy (TCC) blocks background jobs from
 * reading iCloud Drive (the Obsidian vault) unless the executable has Full
 * Disk Access. Granting it to Homebrew's python breaks on every python
 * upgrade, because the real path contains the version number. This launcher's
 * path never changes, so the grant survives upgrades.
 *
 * It must fork and wait (not exec): after an exec the process becomes python
 * and the grant no longer applies.
 *
 * Build:  clang -O2 -o ~/.local/bin/claude-journal-launcher claude_journal_launcher.c
 * Then:   System Settings > Privacy & Security > Full Disk Access > add
 *         ~/.local/bin/claude-journal-launcher
 * Rebuilding changes the binary's signature; if the grant stops working,
 * remove and re-add it.
 */
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <unistd.h>

#define PYTHON "/opt/homebrew/bin/python3"
#define SCRIPT "/Users/mark/mtjb/dotfiles/automation/claude_journal.py"

int main(int argc, char **argv) {
    char *args[argc + 3];
    int n = 0;
    args[n++] = PYTHON;
    args[n++] = SCRIPT;
    for (int i = 1; i < argc; i++) args[n++] = argv[i];
    args[n] = NULL;

    pid_t pid = fork();
    if (pid < 0) { perror("fork"); return 1; }
    if (pid == 0) {
        execv(PYTHON, args);
        perror("execv");
        _exit(127);
    }
    int status = 0;
    if (waitpid(pid, &status, 0) < 0) { perror("waitpid"); return 1; }
    return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}
