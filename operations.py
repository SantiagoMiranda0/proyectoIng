from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import NoResultFound
from models import Game, Player, Tablero, Casilla, engine
from typing import List

from random import shuffle
from fastapi import FastAPI, HTTPException, status, WebSocket, WebSocketDisconnect


class GameNotFoundError(Exception):
    pass

class PlayerNotFoundError(Exception):
    pass

class GameStartedError(Exception):
    pass


Session = sessionmaker(bind = engine)


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




def generar_tablero_aleatorio(id_tablero: int):
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

class Operations: 

    def get_games(self):
        session = Session()
        try:
            games = session.query(Game).all()  # Obtener todos los juegos de la base de datos
            for game in games:
                game.players = game.players
            return games
        finally:
            session.close()

    
    def get_players(self):
        session = Session()
        try:
            # Sacar todos los players
            players = session.query(Player).all()

            return players
        
        finally:
            session.close()


    def get_boards(self):
        session = Session()
        try:
            tableros = session.query(Tablero).all()  # Obtener todos los juegos de la base de datos
            for tablero in tableros:
                tablero.casillas = tablero.casillas
            return tableros
        finally:
            session.close()


    def create_game(self,name: str, cant_players: int, private: bool, password: str):
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
            manager.broadcast("new game created")

            # Devolver el ID y el nombre del juego recién creado
            return {
                'id': new_game_entry.id_partida,
                'name': new_game_entry.name,
                'operation_result': "Successfully created!"
            }

        finally:
            # Cerrar la sesión para liberar los recursos
            session.close()


    def join_game(self,game_id: int, player_id: int):
            # Crear una sesión de la base de datos
        session = Session()
        
        try:
            # Verificar si la partida existe
            game = session.query(Game).filter(Game.id_partida == game_id).first()
            if not game:
                raise GameNotFoundError(f"Game with ID {game_id} not found.")
            
            # Verificar si el jugador existe
            new_player = session.query(Player).filter(Player.id_jugador == player_id).first()
            if not new_player:
                raise PlayerNotFoundError(f"Player with name {player_name} not found.")
            
            # Asociar el jugador a la partida
            game.players.append(new_player)
            
            new_player.id_partida = game.id_partida

            # Marcar el jugador como 'in_game'
            new_player.in_game = True

            # Guardar los cambios
            session.commit()  # ¡IMPORTANTE! Guardar los cambios en la base de datos.
                    
            # Notificar que un jugador se unió
            manager.broadcast("player join")

            # Devolver respuesta exitosa
            return {"message": f"Player {player_id} successfully joined game {game_id}"}

        finally:
            session.close()  # Cerrar la sesión para liberar recursos

    
    def create_player(self, nombre: str):
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

    def delete_game(self,game_id:int):
        session = Session()
        try:
            # Buscar la partida por su ID
            game = session.query(Game).filter(Game.id_partida == game_id).first()
            
            if not game:
                # Si la partida no existe, lanza un error
                raise GameNotFoundError(f"Game with ID {game_id} not found.")
            
            if game.started:
                tablero = session.query(Tablero).filter(Tablero.id_tablero == game.id_tablero).first()
                session.delete(tablero)
            
            # Eliminar la partida
            session.delete(game)
            session.commit()

            return {"message": f"Game with id {game_id} deleted successfully."}
        
        finally:
            session.close()

    def start_game(self,game_id: int):
        session = Session()
        try:
            # Buscar la partida por su ID
            game = session.query(Game).filter(Game.id_partida == game_id).first()

            # Verificar si la partida existe
            if not game:
                raise GameNotFoundError(f"Game with ID {game_id} not found.")

            # Verificar si la partida ya ha comenzado
            if game.started:
                raise GameStartedError(f"Game already on course.")

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










