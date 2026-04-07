import minqlx
class test_time(minqlx.Plugin):
    def __init__(self):
        self.add_command("gametime", self.cmd_gametime)

    def cmd_gametime(self, player, msg, channel):
        game = self.game
        if not game:
            player.tell("No game active.")
            return

        attrs = [attr for attr in dir(game) if not attr.startswith('__')]
        player.tell(f"Game attributes: {', '.join(attrs)}")
