import random
from threading import Thread
from dataclasses import dataclass
from queue import Queue, Empty
from time import sleep
import json


MONITOR_EVENTS_QUEUE = Queue()
ALLOWED_STATES = [
    {"direction_1": "green", "direction_2": "red"},
    {"direction_1": "green", "direction_2": "yellow"},
    {"direction_1": "red", "direction_2": "green"},
    {"direction_1": "red", "direction_2": "yellow"},
    {"direction_1": "yellow", "direction_2": "green"},
    {"direction_1": "yellow", "direction_2": "red"},

    # задание 2
    {"direction_1": "yellow_blinking", "direction_2": "yellow_blinking"},

    # задание 3
    {"direction_1": "green", "direction_1_left": "green", "direction_1_right": "green", "direction_2": "red",
     "direction_2_right": "green"},
    {"direction_1": "red", "direction_1_left": "red", "direction_1_right": "green", "direction_2": "green",
     "direction_2_right": "green"},
]


@dataclass
class Event:
    source: str
    destination: str
    operation: str
    parameters: str

# класс для контроля классов системы светофора, админ команд
@dataclass
class AdminEvent:
    operation: str


# класс, который будут наследовать все системы
class SystemClass(Thread):
    def __init__(self):
        super().__init__()
        self._own_queue = Queue()
        self._admin_queue = Queue()
        self._force_quit: bool = False

    def run(self) -> None:
        print(f"[{self.__class__.__name__}] начал")
        print(f"[{self.__class__.__name__}] закончил")

    def entity_queue(self) -> Queue:
        return self._own_queue

    def stop(self):
        print(f"[{self.__class__.__name__}] Остановка работы")
        request = AdminEvent(operation="stop")
        self._admin_queue.put(request)

    def _check_admin(self):
        try:
            event: AdminEvent = self._admin_queue.get_nowait()
            if event.operation == "stop":
                self._force_quit = True
        except Empty:
            pass


# пустышка
class CitySystemConnector(SystemClass):
    def __init__(self, monitor: Queue):
        super().__init__()
        self.monitor_queue = monitor


class ControlSystem(SystemClass):
    def __init__(self, monitor: Queue):
        super().__init__()
        self.monitor_queue = monitor

    def run(self):
        while not self._force_quit:
            try:
                # генерация варианта режима светофора в отдельном методе
                mode = self._generate_mode()

                event = Event(
                    source=self.__class__.__name__,
                    destination="ModeChecker",
                    operation="set_mode",
                    parameters=json.dumps(mode)
                )
                self.monitor_queue.put(event)
                sleep(3)
            except Empty:
                sleep(0.5)
            finally:
                self._check_admin()

        print(f"[{self.__class__.__name__}] Работа была закончена")

    # генерация режима светофора
    def _generate_mode(self) -> dict:
        colors = ["green", "red", "yellow"]

        mode = {
            "direction_1": random.choice(colors),
            "direction_2": random.choice(colors)
        }
        return mode


class ModeChecker(SystemClass):
    def __init__(self, monitor: Queue, allowed_configurations):
        super().__init__()
        self._allowed = allowed_configurations
        self.monitor_queue = monitor

    def is_allowed(self, mode_str) -> bool:
        if json.loads(mode_str) in self._allowed:
            return True
        else:
            return False

    def run(self):
        print(f"[{self.__class__.__name__}] Начал работу")
        while not self._force_quit:
            try:
                event = self._own_queue.get_nowait()

                if self.is_allowed(event.parameters):

                    print(f"[{self.__class__.__name__}] Изменение режима светофора разрешено")
                    event.source = self.__class__.__name__
                    event.destination = "LightsGPIO"

                    self.monitor_queue.put(event)
                else:
                    print(f"[{self.__class__.__name__}] Такой режим светофора не допустим, изменение отклонено")
            except Empty:
                sleep(0.5)
            except Exception as e:
                print(f"[{self.__class__.__name__}] В ходе выполнения вызвана ошибка - {e}")
            finally:
                self._check_admin()

        print(f"[{self.__class__.__name__}] Работа была закончена")


class Monitor(SystemClass):
    def __init__(self, events_queue: Queue):
        super().__init__()
        self._own_queue: Queue = events_queue
        self._entities = {}

    def add_entity_queue(self, entity_id, entity_queue: Queue):
        print(f"[{self.__class__.__name__}] Регистрация объекта")
        self._entities[entity_id] = entity_queue

    def _check_policies(self, event) -> bool:
        authorized = False

        if event.source == "ControlSystem" \
                and event.destination == "ModeChecker" \
                and event.operation == "set_mode":
            authorized = True
        elif event.source == "ModeChecker" \
                and event.destination == "LightsGPIO" \
                and event.operation == "set_mode":
            authorized = True

        if authorized is False:
            print(f"[{self.__class__.__name__}] Событие не разрешено политиками безопасности")
        return authorized

    def _send_signal(self, event):
        authorized = self._check_policies(event)
        if not authorized:
            return False

        if not isinstance(event, Event):
            return False

        if event.destination not in self._entities:
            print(f"[{self.__class__.__name__}] Я в село молочное не поеду")
            return False

        destination_queue = self._entities[event.destination]
        print(f"[{self.__class__.__name__}] Вы отправляетесь в {event.destination}")
        destination_queue.put(event)
        return True

    def run(self):
        print(f"[{self.__class__.__name__}] Начал работу")
        while not self._force_quit:
            try:
                event = self._own_queue.get_nowait()
                print(f"[{self.__class__.__name__}] Проверяю событие {event}")
                self._send_signal(event)

            except Empty:
                sleep(1)
            except Exception as e:
                print(f"[{self.__class__.__name__}] В ходе выполнения вызвана ошибка - {e}")
            finally:
                self._check_admin()

        print(f"[{self.__class__.__name__}] Работа была закончена")


class LightsGPIO(SystemClass):
    def __init__(self, monitor: Queue):
        super().__init__()
        self.monitor_queue = monitor
        self.current_mode = None

    def run(self):
        while not self._force_quit:
            try:
                event = self._own_queue.get_nowait()

                if event.operation == "set_mode":
                    print(f"[{self.__class__.__name__}] {event.source} запросил изменение светофоров на {event.parameters}")

                    try:
                        self.current_mode = json.loads(event.parameters)
                    except Exception:
                        self.current_mode = None

                    self._print_terminal_state(self.current_mode)

            except Empty:
                sleep(1)
            finally:
                self._check_admin()

        print(f"[{self.__class__.__name__}] Работа была закончена")

    def _print_terminal_state(self, mode: dict) -> None:
        icons = {
            "red": "🔴",
            "yellow": "🟡",
            "green": "🟢",
            "off": "⚫",
            "yellow_blinking": "🟡🟡"
        }

        d1 = icons.get(mode.get("direction_1", "off"), "⚪")
        d2 = icons.get(mode.get("direction_2", "off"), "⚪")

        print(f"[{self.__class__.__name__}] Состояние: direction_1 {d1}  direction_2 {d2}")


def _build_entities():
    mode_checker = ModeChecker(MONITOR_EVENTS_QUEUE, ALLOWED_STATES)
    monitor = Monitor(MONITOR_EVENTS_QUEUE)
    control_system = ControlSystem(MONITOR_EVENTS_QUEUE)
    lights_gpio = LightsGPIO(MONITOR_EVENTS_QUEUE)
    return mode_checker, monitor, control_system, lights_gpio


def _register_entities(monitor: Monitor, control_system: ControlSystem, lights_gpio: LightsGPIO, mode_checker: ModeChecker):
    monitor.add_entity_queue(control_system.__class__.__name__, control_system.entity_queue())
    monitor.add_entity_queue(lights_gpio.__class__.__name__, lights_gpio.entity_queue())
    monitor.add_entity_queue(mode_checker.__class__.__name__, mode_checker.entity_queue())


def main() -> None:
    mode_checker, monitor, control_system, lights_gpio = _build_entities()
    _register_entities(monitor, control_system, lights_gpio, mode_checker)

    mode_checker.start()
    monitor.start()
    control_system.start()
    lights_gpio.start()

    sleep(60)
    control_system.stop()
    lights_gpio.stop()
    monitor.stop()
    mode_checker.stop()

    control_system.join()
    lights_gpio.join()
    monitor.join()
    mode_checker.join()


if __name__ == "__main__":
    main()
