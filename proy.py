from fastapi import FastAPI, HTTPException, status, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import NoResultFound
from games import Game, Base, Player, Tablero, Casilla, Session, engine   # Modelos de SQLAlchemy
from random import shuffle
from enum import Enum
from typing import List



app= FastAPI()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.get("/gamelist")
async def get_gamelist():
    session = Session()
    try:
        games = session.query(Game).all()  # Obtener todos los juegos de la base de datos
        for game in games:
            game.players = game.players
        return games
    finally:
        session.close()



@app.post(
    "/gamelist",
    status_code=status.HTTP_201_CREATED)
async def create_game(name: str, cant_players: int, private: bool, password: str):
    # Crear una sesión de la base de datos
    session = Session()
    try:
        # Crear una nueva instancia de Game con el tablero en NULL
        new_game_entry = Game(
            name=name,
            cant_jugadores=cant_players,
            started=False,
            is_private=private,
            password=password,
            id_tablero=None  # El tablero aún no está asignado, así que se deja en NULL
        )

        # Agregar el nuevo juego a la sesión
        session.add(new_game_entry)
        # Guardar los cambios en la base de datos
        session.commit()
        # Refrescar la instancia para obtener el id generado automáticamente
        session.refresh(new_game_entry)

        # Enviar una señal por WebSocket a todos los clientes conectados
        await manager.broadcast("new game created")

        # Devolver el ID y el nombre del juego recién creado
        return {
            'id': new_game_entry.id_partida,
            'name': new_game_entry.name,
            'operation_result': "Successfully created!"
        }

    finally:
        # Cerrar la sesión para liberar los recursos
        session.close()

@app.put("/gamelist/join/{game_id}", status_code=status.HTTP_200_OK)
async def join_game(game_id: int, player_id: int):
    # Crear una sesión de la base de datos
    session = Session()
    
    try:
        # Verificar si la partida existe
        game = session.query(Game).filter(Game.id_partida == game_id).first()
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        
        # Verificar si el jugador existe
        new_player = session.query(Player).filter(Player.id_jugador == player_id).first()
        if not new_player:
            raise HTTPException(status_code=404, detail="Player not found")
        
        # Asociar el jugador a la partida
        game.players.append(new_player)
        
        new_player.id_partida = game.id_partida

        # Marcar el jugador como 'in_game'
        new_player.in_game = True

        # Guardar los cambios
        session.commit()  # ¡IMPORTANTE! Guardar los cambios en la base de datos.

        # Notificar que un jugador se unió
        await manager.broadcast("player join")

        # Devolver respuesta exitosa
        return {"message": f"Player {player_id} successfully joined game {game_id}"}

    finally:
        session.close()  # Cerrar la sesión para liberar recursos



@app.post("/", status_code=status.HTTP_201_CREATED)
async def create_player(nombre: str):
    session = Session()
    try:
        new_player_entry = Player(
            nombre=nombre
        )
        session.add(new_player_entry)
        session.commit()
        session.refresh(new_player_entry)
        return {
            'id': new_player_entry.id_jugador,
            'name': new_player_entry.nombre,
            'operation_result': "Successfully created!"
        }
    finally:
        session.close()

@app.delete("/gamelist/{game_id}")
async def delete_game(game_id: int):
    session = Session()
    try:
        # Buscar la partida por su ID
        game = session.query(Game).filter(Game.id_partida == game_id).first()
        
        if not game:
            # Si la partida no existe, lanza un error 404
            raise HTTPException(status_code=404, detail="Game not found")
        
        # Eliminar la partida
        session.delete(game)
        session.commit()

        return {"message": f"Game with id {game_id} deleted successfully."}
    
    finally:
        session.close()



@app.get("/players")
async def delete_game():
    session = Session()
    try:
        # Sacar todos los players
        players = session.query(Player).all()

        return players
    
    finally:
        session.close()


def generar_tablero_aleatorio(id_tablero):
    # Los 4 colores que se van a distribuir equitativamente
    colores = ['rojo', 'azul', 'verde', 'amarillo']

    # Crear una lista con 9 repeticiones de cada color para llenar el tablero
    lista_colores = colores * 9
    shuffle(lista_colores)  # Barajar los colores aleatoriamente

    # Crear los casilleros y asignar colores
    session = Session()
    try: 
        tablero = session.query(Tablero).filter(Tablero.id_tablero == id_tablero).first() 
        for fila in range(6):
            for columna in range(6):
                # Extraer un color de la lista barajada
                color = lista_colores.pop()

                # Crear un casillero en la posición (fila, columna) con el color asignado
                casilla = Casilla(
                    fila=fila,
                    columna=columna,
                    color=color,
                    id_tablero=id_tablero  # Relación con el tablero
                )
                session.add(casilla)
                tablero.casillas.append(casilla)

        session.commit()  # Guardar todos los casilleros en la base de datos
    finally:
        session.close()

    return {"message": "Tablero generado con éxito"}

@app.put("/gamelist/start/{game_id}")
async def start_game(game_id: int):
    session = Session()
    try:
        # Buscar la partida por su ID
        game = session.query(Game).filter(Game.id_partida == game_id).first()

        # Verificar si la partida existe
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")

        # Verificar si la partida ya ha comenzado
        if game.started:
            raise HTTPException(status_code=400, detail="Game has already started")

        # Crear un nuevo tablero para la partida
        nuevo_tablero = Tablero()
        session.add(nuevo_tablero)
        session.commit()  # Guardar el tablero y obtener su id
        session.refresh(nuevo_tablero)

        # Asignar el tablero a la partida
        game.id_tablero = nuevo_tablero.id_tablero
        game.started = True  # Marcar que la partida ha comenzado
        session.commit()  # Guardar los cambios en la partida

        # Generar los casilleros y asignar colores aleatorios al tablero
        generar_tablero_aleatorio(nuevo_tablero.id_tablero)

        return {"message": f"Game {game_id} has started successfully!"}
    
    finally:
        session.close()

@app.get("/tableros")
async def print_tablero():
    session = Session()
    try:
        tableros = session.query(Tablero).all()  # Obtener todos los juegos de la base de datos
        for tablero in tableros:
            tablero.casillas = tablero.casillas
        return tableros
    finally:
        session.close()

        
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(f"Message text was: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)