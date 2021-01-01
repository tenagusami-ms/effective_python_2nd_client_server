from __future__ import annotations

import contextlib
import math
import random
import socket
from threading import Thread
from typing import Sequence, Optional, List, Generator, Any, Tuple, Iterable, BinaryIO


def main():
    address: Tuple[Optional[str], int] = ("127.0.0.1", 1234)
    server_thread: Thread = Thread(target=run_server, args=(address,), daemon=True)
    server_thread.start()
    results: Iterable[Tuple[int, str]] = run_client(address)
    for number, outcome in results:
        print(f"Client: {number} is {outcome}")


class ConnectionBase:
    def __init__(self, connection: socket.socket):
        self.connection: socket.socket = connection
        self.file: BinaryIO = connection.makefile("rb")

    def send(self, command: str):
        line: str = command + "\n"
        data: bytes = line.encode()
        self.connection.send(data)

    def receive(self) -> str:
        data: bytes = self.file.readline()
        if not data:
            raise EOFError("Connection closed")
        return data[:-1].decode()


WARMER: str = "Warmer"
COLDER: str = "Colder"
UNSURE: str = "Unsure"
CORRECT: str = "Correct"


class UnknownCommandError(Exception):
    pass


class Session(ConnectionBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.secret: Optional[int] = None
        self._clear_state(None, None)

    def _clear_state(self, lower: Optional[int], upper: Optional[int]) -> None:
        self.lower: Optional[int] = lower
        self.upper: Optional[int] = upper
        self.secret = None
        self.guesses: List[int] = []

    def loop(self):
        while command := self.receive():
            parts: Sequence[str] = command.split(" ")
            command: str = next(iter(parts))
            if command == "PARAMS":
                self.set_params(parts)
            elif command == "NUMBER":
                self.send_number()
            elif command == "REPORT":
                self.receive_report(parts)
            else:
                raise UnknownCommandError(command)

    def set_params(self, parts: Sequence[str]) -> None:
        assert len(parts) == 3
        lower = int(parts[1])
        upper = int(parts[2])
        self._clear_state(lower, upper)

    def next_guess(self):
        if self.secret is not None:
            return self.secret
        while True:
            guess: int = random.randint(self.lower, self.upper)
            if guess not in self.guesses:
                return guess

    def send_number(self):
        guess = self.next_guess()
        self.guesses.append(guess)
        self.send(format(guess))

    def receive_report(self, parts: Sequence[str]) -> None:
        assert len(parts) == 2
        decision: str = parts[1]
        last: int = self.guesses[-1]
        if decision == CORRECT:
            self.secret = last
        print(f"Server: {last} is {decision}")


class Client(ConnectionBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.last_distance: Optional[int] = None
        self.secret: Optional[int] = None
        self._clear_state()

    def _clear_state(self) -> None:
        self.secret = None
        self.last_distance = None

    @contextlib.contextmanager
    def session(self, lower: int, upper: int, secret: int) -> Generator[None, Any, None]:
        print(f"Guess a number between {lower} and {upper}"
              f" Shhhhh, it's {secret}.")
        self.secret = secret
        self.send(f"PARAMS {lower} {upper}")
        try:
            yield
        finally:
            self._clear_state()
            self.send("PARAMS 0 -1")

    def request_numbers(self, count: int) -> Generator[int, Any, None]:
        for _ in range(count):
            self.send("NUMBER")
            data: str = self.receive()
            yield int(data)
            if self.last_distance == 0:
                return

    def report_outcome(self, number: int) -> str:
        new_distance: float = math.fabs(number - self.secret)
        decision: str = UNSURE

        if new_distance == 0:
            decision = CORRECT
        elif self.last_distance is None:
            pass
        elif new_distance < self.last_distance:
            decision = WARMER
        elif new_distance > self.last_distance:
            decision = COLDER
        self.last_distance = new_distance
        self.send(f"REPORT {decision}")
        return decision


def handle_connection(connection) -> None:
    with connection:
        session: Session = Session(connection)
        try:
            session.loop()
        except EOFError:
            pass


def run_server(address: Tuple[Optional[str], int]) -> None:
    with socket.socket() as listener:
        listener.bind(address)
        listener.listen()
        while True:
            connection, _ = listener.accept()
            thread: Thread = Thread(target=handle_connection,
                                    args=(connection,),
                                    daemon=True)
            thread.start()


def run_client(address: Tuple[Optional[str], int]) -> Iterable[Tuple[int, str]]:
    with socket.create_connection(address) as connection:
        client: Client = Client(connection)

        with client.session(1, 5, 3):
            results: List[Tuple[int, str]] = [(x, client.report_outcome(x))
                                              for x in client.request_numbers(5)]
        with client.session(10, 15, 12):
            for number in client.request_numbers(5):
                outcome = client.report_outcome(number)
                results.append((number, outcome))
    return results


if __name__ == '__main__':
    main()
