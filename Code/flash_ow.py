"""Flash the 1-Wire identity EEPROM of a Crazyflie expansion deck.

The target deck is the DECK constant below. Mount the deck before powering the
drone on, and power cycle after flashing.
"""

import logging
import sys
import threading

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.crazyflie.mem import MemoryElement

URI = 'radio://0/90/2M/E7E7E7E711'
VID = 0xBC
BOARD_REV = 'b'
TIMEOUT = 20

# From deck_core.h:48-74. Bits 0-12 pins, 13-18 peripherals (timers included).
IO2, IO3, TIMER3 = 1 << 5, 1 << 6, 1 << 13

# name -> (pid, pins), mirroring the driver's usedGpio|usedPeriph.
# No bit exists for power (VCC/VCOM) or nRF51 IOs, hence 0 for the Qi.
DECKS = {
    'bcLedRing': (0x01, IO2 | IO3 | TIMER3),
    'bcQi':      (0x02, 0),
}

# Deck to flash
DECK = 'bcLedRing'
PID, PINS = DECKS[DECK]


def _block(what, call):
    """Run a callback-based memory operation and wait for it to finish."""
    done = threading.Event()
    call(lambda *_: done.set())
    if not done.wait(TIMEOUT):
        raise TimeoutError(f'{what} timed out after {TIMEOUT}s')


def read(deck):
    # update() resets deck.valid but not deck.elements, which is accumulated
    # into -- stale keys would fake a successful read-back.
    deck.elements.clear()
    _block('read', deck.update)


def show(deck):
    if not deck.valid:
        return '  <blank or bad CRC>'
    header = f'  {deck.vid:#04x}:{deck.pid:#04x}  pins={deck.pins:#010x}'
    body = [f'  {k}: {v}' for k, v in sorted(deck.elements.items())]
    return '\n'.join([header] + body)


def flash(scf):
    mems = scf.cf.mem.get_mems(MemoryElement.TYPE_1W)
    if not mems:
        raise RuntimeError('No 1-Wire memory found -- is the deck mounted?')
    deck = mems[0]

    read(deck)
    print('Before:\n' + show(deck))

    # write_data() serialises all four fields; pins defaults to None, and a
    # blank EEPROM leaves vid/pid holding whatever garbage was read.
    deck.vid, deck.pid, deck.pins = VID, PID, PINS
    deck.elements['Board name'] = DECK
    deck.elements['Board revision'] = BOARD_REV
    _block('write', deck.write_data)

    read(deck)
    print('After:\n' + show(deck))

    if not (deck.valid and deck.vid == VID and deck.pid == PID
            and deck.elements.get('Board name') == DECK
            and deck.elements.get('Board revision') == BOARD_REV):
        raise RuntimeError('Read-back does not match what was written')

    print('\nDone. Power cycle the drone.')


def main():
    logging.basicConfig(level=logging.ERROR)
    cflib.crtp.init_drivers()

    print(f'Target: {DECK} {VID:#04x}:{PID:#04x} pins={PINS:#010x}')
    print(f'Connecting to {URI}...')
    with SyncCrazyflie(URI, cf=Crazyflie(rw_cache='./cache')) as scf:
        # open_link() returns before mem.refresh() has run, so get_mems()
        # would come back empty; this waits for the full sequence.
        scf.wait_for_params()
        flash(scf)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        sys.exit(f'Error: {exc}')