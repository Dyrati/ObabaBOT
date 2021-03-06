from ..utilities import client, command, reply, set_buttons, clear_buttons

def v_iter(array):
    for x, col in enumerate(array):
        out = []
        for y, piece in enumerate(col):
            out.append((piece, x, y))
        yield out

def h_iter(array):
    array = zip(*array)
    for y, row in enumerate(array):
        out = []
        for x, piece in enumerate(row):
            out.append((piece, x, y))
        yield out

def diag_iter(array):
    up = lambda x,y: (x, y+1)
    down = lambda x,y: (x, y-1)
    left = lambda x,y: (x-1, y)
    right = lambda x,y: (x+1, y)
    upleft = lambda x,y: (x-1, y+1)
    upright = lambda x,y: (x+1, y+1)
    ismember = lambda x,y: 0 <= x < len(array) and 0 <= y < len(array[0])
    positions = ((0,0), (len(array)-1,1), (len(array)-1,0), (0,1))
    shifts = (right, up, left, up)
    directions = (upleft, upleft, upright, upright)
    for pos, shift, direction in zip(positions, shifts, directions):
        while ismember(*pos):
            x, y = pos
            out = []
            while ismember(x,y):
                out.append((array[x][y], x, y))
                x,y = direction(x,y)
            yield out
            pos = shift(*pos)


class ConnectFour():
    def __init__(self, width=7, height=6, connect=4):
        self.current_player = 1
        self.board = [["   " for i in range(height)] for j in range(width)]
        self.pieces = [" X "," O "]
        self.connect = connect
        self.count = 0
        self.previous = None
        self.end = False
    
    def add_piece(self, col):
        if "   " not in self.board[col]: return
        height = self.board[col].index("   ")
        piece = self.pieces[self.current_player-1]
        self.board[col][height] = piece
        self.count += 1
        self.previous = (piece, col, height)
        if self.check_win(): return self.current_player
        if self.check_tie(): return 0
        self.current_player += 1
        if self.current_player > 2: self.current_player = 1

    def reset(self):
        for col in self.board:
            col[:] = ["   " for i in range(6)]

    def check_win(self):
        copy = [col[:] for col in self.board]
        for iterator in (v_iter, h_iter, diag_iter):
            for line in iterator(copy):
                pieces, xcoords, ycoords = zip(*line)
                s = "".join(pieces)
                for piece in self.pieces:
                    if piece*self.connect in s:
                        start = s.index(piece*self.connect)//len(piece)
                        for p,x,y in line[start:]:
                            if p == piece: self.board[x][y] = f"({piece[1:-1]})"
                            else: break
                        self.end = True
        return self.end

    def check_tie(self):
        if self.count == len(self.board)*len(self.board[0]):
            self.end = True
        return self.end
    
    def __str__(self):
        copy = [col[:] for col in self.board]
        if self.previous and not self.end:
            p,x,y = self.previous
            copy[x][y] = f"'{p[1:-1]}'"
        rows = [f" |{'|'.join(row)}|" for row in zip(*copy)]
        spacing = len(rows[0])-1
        border = " " + "="*spacing
        legs = " |/"+" "*(spacing-3)+"|/"
        feet = "//"+" "*(spacing-3)+"//"
        return "\n".join((border, "\n".join((reversed(rows))), border, legs, feet))


@command
async def connect4(message, *args, **kwargs):
    """Begins a game of connect 4
    
    Keyword Arguments:
        width -- width of game board, ranges from 1 to 10
        height -- height of game board, ranges from 1 to 10
        connect -- the number of connected pieces required to win
        notify -- ping the first player when a game has started
    """
    defaults = {"width":7, "height":6, "connect":4}
    dimensions = {k:int(v) for k,v in kwargs.items() if k in defaults}
    for k,v in defaults.items(): dimensions.setdefault(k,v)
    assert dimensions["width"] <= 10 and dimensions["height"] <= 10, "Dimensions too large"
    game = ConnectFour(**dimensions)
    width = len(str(game).split("\n",1)[0])
    players = []
    create_task = client.loop.create_task

    def header():
        names = "{}  vs  {}".format(*(p.name for p in players))
        left, right = names.center(width).split(names)
        if game.current_player == 1: left = left[:-2] + "► "
        elif game.current_player == 2: right = " ◄" + right[2:]
        return left + names + right + "\n\n"

    async def startphase(message, user, button):
        if button == True:
            players.append(user)
        elif button == False and user in players:
            players.remove(user)
        if len(players) < 2:
            content = " " + "\n ".join((player.name + " has joined!" for player in players))
            content += f"\n Waiting for Player {len(players)+1} to join\n\n{game}"
            await message.edit(content=f"```\n{content}\n```")
        else:
            content = players[0].mention if kwargs.get("notify") else ""
            content += f"```\n{header()}{game}\n```"
            t1 = create_task(message.edit(content=content))
            buttons = {f"{i}\ufe0f\u20e3": i for i in range(dimensions["width"])}
            t2 = create_task(set_buttons(message, buttons, mainphase))
            await t1, t2

    async def mainphase(message, user, button):
        if user != players[game.current_player-1]: return
        wincheck = game.add_piece(button)
        player = players[game.current_player-1]
        if wincheck is not None:
            if wincheck == 0: content = "Tie Game".center(width+1) + f"\n\n{game}"
            else: content =  f"{player.name} wins!".center(width+1) + f"\n\n{game}"
            t1 = create_task(message.edit(content=f"```\n{content}\n```"))
            t2 = create_task(clear_buttons(message))
            await t1, t2
        else:
            await message.edit(content=f"```\n{header()}{game}\n```")

    content = f" \n Waiting for Player {len(players)+1} to join\n\n{game}"
    sent = await reply(message, f"```\n{content}\n```")
    await set_buttons(sent, {"\u2705":True, "\u274c":False}, startphase)
