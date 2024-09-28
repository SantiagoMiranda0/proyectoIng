from fastapi import FastAPI, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.exc import NoResultFound
from operations import Operations, GameNotFoundError, PlayerNotFoundError, GameStartedError, ConnectionManager

from enum import Enum
from typing import List



app= FastAPI()


@app.get("/gamelist")
async def print_games():
    operation = Operations()

    return operation.get_games()


@app.get("/players")
async def print_players():
    operation = Operations()

    return operation.get_players()

@app.get("/tableros")
async def print_tableros():
    operation = Operations()
    
    return operation.get_boards()



@app.post("/gamelist")
async def create_game(name: str, cant_players: int, private: bool, password: str):
    operation = Operations()

    return operation.create_game(name=name,cant_players=cant_players,private=private,password=password)




@app.put("/gamelist/join/{game_id}")
async def join_game(game_id: int, player_id: int):
    operation = Operations()
    try:

        return operation.join_game(game_id=game_id, player_id=player_id)

    except GameNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except PlayerNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))  



@app.post("/",)
async def create_player(nombre: str):
    operation = Operations()
    
    return operation.create_player(nombre=nombre)
    

@app.delete("/gamelist/{game_id}")
async def delete_game(game_id: int):
    operation = Operations()
    try: 
        return operation.delete_game(game_id=game_id)

    except GameNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))



@app.put("/gamelist/start/{game_id}")
async def start_game(game_id: int):
    operation = Operations()
    try:
        return operation.start_game(game_id=game_id)
    
    except GameNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except GameStartedError as e:
        raise HTTPException(status_code=400, detail=str(e))



@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(f"Message text was: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)