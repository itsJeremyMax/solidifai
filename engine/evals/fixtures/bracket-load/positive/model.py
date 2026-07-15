from build123d import Box, Cylinder, Pos

from solidifai import show

bracket = Box(6, 50, 52) + Pos(15, 0, -22) * Box(30, 50, 8)
bracket -= Pos(0, -20, 0) * Cylinder(2.75, 10, rotation=(0, 90, 0))
bracket -= Pos(0, 20, 0) * Cylinder(2.75, 10, rotation=(0, 90, 0))
fillets = [
    edge
    for edge in bracket.edges()
    if (
        abs(edge.center().X - 3) < 0.1
        and abs(abs(edge.center().Y) - 25) < 0.1
        and abs(edge.center().Z - 4) < 0.2
    )
    or (
        abs(edge.center().X - 16.5) < 0.2
        and abs(abs(edge.center().Y) - 25) < 0.1
        and abs(edge.center().Z + 18) < 0.2
    )
    or (
        abs(edge.center().X - 3) < 0.1
        and abs(edge.center().Y) < 0.1
        and abs(edge.center().Z + 18) < 0.2
    )
]
bracket = bracket.fillet(radius=2, edge_list=fillets)
show(bracket, name="bracket")
