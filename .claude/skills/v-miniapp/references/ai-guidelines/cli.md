# CLI Guidelines

Critical guidelines for AI assistants when executing CLI commands in V-MiniApp projects.

---

## Interactive CLI Commands

**CRITICAL:** AI assistants cannot pause and wait for user input during interactive CLI commands. When encountering commands that require user interaction:

1. **Use non-interactive flags/options** when available:

   - For `create`: Use `--css`, `--pm`, `--install`, `--token` to avoid prompts
   - Example: `v-miniapp-cli create my-app --css tailwind --pm npm --install --token <token>`

2. **When any selection prompt appears** (framework, CSS, package manager, or any other option selection):

   - **ALWAYS use `expect` script to automatically select the first option**
   - Create a temporary expect script that automatically sends Enter (`\r`) when prompted
   - The expect script should continuously send Enter to auto-select the first/default option for all prompts
   - Run the expect script to handle all interactive prompts automatically
   - Do NOT ask user to run commands manually - automate everything

3. **Expect Script Template for Auto-Selection:**

   When creating an expect script to handle interactive prompts, **always configure it to send Enter (`\r`) to automatically select the first option** for any prompt that appears:

   ```bash
   #!/usr/bin/expect -f
   set timeout 120
   set project_name [lindex $argv 0]
   if {$project_name == ""} { set project_name "my-miniapp" }

   spawn v-miniapp-cli create $project_name --css tailwind --pm npm --install

   # Continuously send Enter to auto-select first/default option
   # This will automatically accept all default selections
   expect {
       -re "." {
           send "\r"
           exp_continue
       }
       timeout {
           send "\r"
           exp_continue
       }
       eof
   }

   set exit_code [wait]
   exit [lindex $exit_code 3]
   ```

   **Key points:**

   - The script automatically sends Enter (`\r`) whenever any prompt appears
   - This selects the first/default option for all interactive prompts
   - No user interaction required - fully automated

4. **Fallback:** If expect is not available, create project structure manually based on React + TypeScript + Tailwind template, then run dev server

---

## Authentication & Session Management

**CRITICAL:** Authentication is required before most CLI operations. Always check and ensure login session exists before executing commands.

**Workflow:**

1. **Login first** (one-time setup): `v-miniapp-cli login` - This creates a session that persists for subsequent commands
2. **Then proceed** with other operations: `create`, `dev`, `build`, `deploy`

**When to run login:**

- Before `create` command (required)
- Before `dev` command (required for authenticated features)
- Before `deploy` command (required)
- If user encounters authentication errors, prompt them to run `login` first

**Alternative:** Users can use `--token <token>` option with commands instead of running `login` separately, but `login` is the standard workflow.

**Remember:** Once logged in, the session persists. Users don't need to login again for each command unless they logout or the session expires.
