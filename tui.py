import json
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.layout import Layout
from rich.align import Align


class TUI:
    """A Text-based User Interface for the agent."""

    def __init__(self):
        """Initializes the TUI."""
        self.console = Console()

    def start_live_display(self):
        """Starts a live display for showing agent activity."""
        self.console.print("[bold blue]Thinking...[/bold blue]")

    def stop_live_display(self):
        """Stops the live display."""
        pass

    def display_message(self, role: str, message: str):
        """
        Displays a message from the user or the model.

        Args:
            role: The role of the message sender ('user' or 'model').
            message: The message content.
        """
        color = "green" if role == "user" else "blue"
        if role == "system":
            color = "yellow"

        panel = Panel(
            message,
            title=f"[bold {color}]{role.capitalize()}[/bold {color}]",
            border_style=color,
        )
        self.console.print(panel)

    def display_tool_call(self, tool_name: str, tool_args: dict):
        """
        Displays a tool call requested by the model.

        Args:
            tool_name: The name of the tool being called.
            tool_args: The arguments for the tool call.
        """
        args_str = json.dumps(tool_args, indent=2)
        syntax = Syntax(args_str, "json", theme="monokai", line_numbers=True)
        panel = Panel(
            syntax,
            title=f"[bold yellow]Tool Call: {tool_name}[/bold yellow]",
            border_style="yellow",
        )
        self.console.print(panel)

    def display_tool_output(self, tool_name: str, output: dict):
        """
        Displays the output of a tool call.

        Args:
            tool_name: The name of the tool that was called.
            output: The output from the tool.
        """
        output_str = json.dumps(output, indent=2)

        syntax = Syntax(output_str, "json", theme="monokai", line_numbers=True)
        panel = Panel(
            syntax,
            title=f"[bold magenta]Tool Output: {tool_name}[/bold magenta]",
            border_style="magenta",
        )
        self.console.print(panel)

    def display_error(self, error_message: str):
        """
        Displays an error message.

        Args:
            error_message: The error message to display.
        """
        panel = Panel(
            error_message, title="[bold red]Error[/bold red]", border_style="red"
        )
        self.console.print(panel)

    def get_user_input(self, prompt: str = "\n[bold green]You:[/bold green] ") -> str:
        """
        Gets input from the user.

        Args:
            prompt: The prompt to display to the user.

        Returns:
            The user's input.
        """
        return self.console.input(prompt)

    def get_confirmation(self, prompt: str) -> bool:
        """
        Gets a yes/no confirmation from the user.

        Args:
            prompt: The confirmation prompt to display.

        Returns:
            True if the user confirms, False otherwise.
        """
        while True:
            response = self.console.input(
                f"[bold yellow]{prompt} (y/n): [/bold yellow]"
            ).lower()
            if response in ["y", "yes"]:
                return True
            elif response in ["n", "no"]:
                return False

    def display_welcome(self):
        """Displays a welcome message."""
        layout = Layout()
        layout.split(Layout(name="header", size=3), Layout(ratio=1, name="main"))
        layout["main"].update(
            Align.center(
                "[bold blue]Welcome to the Autonomous Lightning Network Agent[/bold blue]\n"
                "Type your commands below. Type 'exit' or 'quit' to end the session.",
                vertical="middle",
            )
        )
        self.console.print(layout)
        self.console.print()
