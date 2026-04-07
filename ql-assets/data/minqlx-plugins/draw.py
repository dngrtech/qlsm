import minqlx

class draw(minqlx.Plugin):
    """MinQLX Plugin to slay all players on Red and Blue teams."""

    def __init__(self):
        self.add_command("draw", self.cmd_draw, 3)

    @minqlx.next_frame
    def slay_all(self):
        """Slays all players on the Red and Blue teams in the next frame."""
        # Iterate over all players and slay only those on Red or Blue teams
        for p in self.players():
            if p.team in ['red', 'blue']:
                self.slay(p)
                p.tell("Forcing round draw")
        self.unpause()

    def cmd_draw(self, player, msg, channel):
        """Command handler to invoke slaying of players on the Red and Blue teams."""
        # Check if there are any players on the Red or Blue teams
        if not any(p.team in ['red', 'blue'] for p in self.players()):
            player.tell("There are no players on Red or Blue teams.")
        else:
            # Schedule slay_all to run on the next frame
            self.slay_all()
            player.tell("Forcing round draw")
        

