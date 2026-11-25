#!/usr/bin/env python3
"""Exercise original game paths without a window or touching the player's save.

Stage completion, death and special-stage results are injected at their original
state boundaries. These are integration checks, not a recorded full playthrough
or evidence of pixel/cycle equivalence with the Windows executable.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.runtime import Game, A, START, UP, DOWN, LEFT, RIGHT


def signed(value):
    return ctypes.c_int32(value).value


def force_state(game, state, substate=0):
    game.write(0x610874, state & 0xffffffff)
    game.write(0x610878, substate & 0xffffffff)


def finish_tally(game):
    game.until(lambda g: signed(g.read(0x4ea130)) < -49, limit=5000)
    game.step(A)
    game.step()


class CoreIntegration(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="sonic3d-test-")
        self.old_save_dir = os.environ.get("SONIC3D_SAVE_DIR")
        os.environ["SONIC3D_SAVE_DIR"] = self.directory.name

    def tearDown(self):
        if self.old_save_dir is None:
            os.environ.pop("SONIC3D_SAVE_DIR", None)
        else:
            os.environ["SONIC3D_SAVE_DIR"] = self.old_save_dir
        self.directory.cleanup()

    def test_boot_input_audio_and_pause(self):
        with Game() as game:
            game.new_game()
            self.assertEqual((game.info.width, game.info.height), (320, 224))
            self.assertEqual(game.info.music_track, 5)
            before = game.sonic
            game.step(RIGHT, 45)
            self.assertNotEqual((game.sonic["x"], game.sonic["y"]), (before["x"], before["y"]))
            game.events.clear()
            game.step(A, 12)
            self.assertTrue(any(e[1] == 1 for e in game.events), "jump must emit a sound event")
            game.step()
            game.step(START)
            game.until(lambda g: g.info.state == 50000)
            game.step(frames=120)
            paused = game.sonic
            game.step(RIGHT, 60)
            self.assertEqual(game.sonic, paused)
            game.step(START)
            game.step()
            game.until(lambda g: g.info.state == 10000)
            self.assertEqual(game.info.music_track, 5)
            self.assertGreater(len(set(game.pixels)), 32)

    def test_regular_and_boss_stages(self):
        codes = [0x1a, 0x1b, 0x1c, 0x2b, 0x2a, 0x2c, 0x3a, 0x3b, 0x3c,
                 0x5a, 0x5b, 0x5c, 0x4b, 0x4a, 0x4c, 0x6a, 0x6b, 0x6c,
                 0x7a, 0x7b, 0x7c]
        for index, code in enumerate(codes, 1):
            with self.subTest(level=index), Game() as game:
                game.new_game(index)
                self.assertEqual(game.read(0x5eaaec, 2), code)
                for keys in (RIGHT, RIGHT | A, DOWN, LEFT, LEFT | A, UP, 0):
                    game.step(keys, 30)
                self.assertIn(game.info.state, (10000, 6, -5, 5))
                self.assertGreater(len(set(memoryview(game.pixels).cast("I"))), 2)

    def test_act_progression_and_autosave(self):
        for level in (1, 2, 3, 19, 20, 21):
            with self.subTest(level=level), Game() as game:
                game.new_game(level)
                game.write_be(0x4d0350, 0)  # no rings: keep score tally short
                game.write_be(0x4d06c4, 1)  # original level-complete flag
                game.until(lambda g: g.info.state == 9)
                game.until(lambda g: g.info.substate in (1, 2, 3))
                finish_tally(game)
                game.until(lambda g: g.info.state in (10000, 1001, 1002), limit=2000)
                self.assertEqual(game.be(0x4d0324), level + 1)
                self.assertEqual(game.info.state, 1002 if level == 21 else 10000)
                self.assertTrue((Path(self.directory.name) / "pcsonic.sav").is_file())

    def test_boss_flash_palette_cleanup_across_zones(self):
        with Game() as game:
            game.new_game(3)
            # Invoke the original boss hit-flash routine with an active hit.
            game.write(0x4d0030, 0x4de428)
            game.write_be(0x4de428 + 0x38, 2)
            game.write_be(0x4de428 + 0x3a, 1)
            game.call(0x45c37c)
            self.assertEqual(game.be(0x4d06d4), 0x0fff)
            game.step(frames=5)
            self.assertEqual(game.read(0xa05264) & 1, 1,
                             "active boss flashes must still alternate palettes")

            game.write_be(0x4d0350, 0)
            game.write_be(0x4d06c4, 1)
            game.until(lambda g: g.info.state == 9)
            game.until(lambda g: g.info.substate in (1, 2, 3))
            finish_tally(game)
            game.until(lambda g: g.info.state == 10000, limit=2000)
            game.until(lambda g: g.read(0x61071c) == 0, limit=600)
            game.step(frames=10)
            self.assertEqual(game.be(0x4d0324), 4)
            self.assertEqual(game.be(0x4d06d4), 0)
            self.assertEqual(game.read(0xa05264), 0,
                             "finished flashes must not leak into the next zone")

            # The monitor casing and base share palette bank 3 with badniks.
            # A stale odd flash counter selects the rainbow boss bank (0x700).
            monitor_palettes = {}
            for index in range(game.read(0x610654)):
                sprite = 0x5eb6ec + index * 32
                art = game.read(sprite + 4, 2)
                if art in (0x5758, 0x57d8):
                    monitor_palettes[art] = game.read(sprite + 6, 2) & 0x7ff
            self.assertEqual(monitor_palettes, {0x5758: 0x300, 0x57d8: 0x300})

    def test_special_stages_and_rewards(self):
        lengths = [960, 1100, 1250, 1400, 1550, 1700, 1920]
        targets = [100, 150, 200, 250, 300, 400, 500]
        for stage in range(7):
            with self.subTest(stage=stage), Game() as game:
                game.new_game()
                game.write_be(0x4d034c, stage)
                force_state(game, 1006)
                game.until(lambda g: g.state == (1006, 1))
                game.step(frames=240)
                self.assertEqual(game.read(0x881760), stage)
                self.assertEqual(game.read(0x881764), lengths[stage])
                self.assertEqual(game.read(0x881934), targets[stage])
                self.assertEqual(game.info.music_track, 19)
                self.assertGreater(len(set(game.pixels)), 32)
        for gems, repeat, success in ((0, 0, False), (0, 0, True), (3, 0, True),
                                       (3, 1, True), (7, 0, True)):
            with self.subTest(gems=gems, repeat=repeat, success=success), Game() as game:
                game.new_game()
                game.write_be(0x4d034c, gems)
                game.write(0x6106b0, repeat)
                lives = game.be(0x4d0326)
                force_state(game, 1006)
                game.until(lambda g: g.state == (1006, 1))
                game.step(frames=120)
                target, length = game.read(0x881934), game.read(0x881764)
                game.write(0x881930, target if success else 0)
                # The original update advances the final unit itself.
                game.write(0x881740, (length + (53 if success else 0)) * 64)
                game.write(0x881870, length + (53 if success else 0))
                game.until(lambda g: g.info.state != 1006)
                gem_award = int(success and not repeat and gems < 7)
                life_award = int(success and (repeat or gems >= 7))
                self.assertEqual(game.read(0x6107c8), gem_award)
                self.assertEqual(game.read(0x6107cc), life_award)
                game.until(lambda g: g.state == (10, 1))
                finish_tally(game)
                game.until(lambda g: g.info.state == 10000)
                self.assertEqual(game.be(0x4d034c), gems + gem_award)
                self.assertEqual(game.be(0x4d0326), lives + life_award)

    def test_death_continue_and_game_over(self):
        for lives, continues in ((3, 0), (0, 0), (0, 1)):
            with self.subTest(lives=lives, continues=continues), Game() as game:
                game.new_game()
                game.write_be(0x4d0326, lives)
                game.write_be(0x4d0354, continues)
                game.write_be(0x4dcba0, 1)
                game.step()
                game.until(lambda g: g.info.state in (7, 8, 10000), limit=2000)
                if lives:
                    self.assertEqual(game.info.state, 10000)
                    self.assertEqual(game.be(0x4d0326), lives - 1)
                elif continues:
                    game.until(lambda g: g.state == (7, 1))
                    game.step(frames=130)
                    game.step(A)
                    game.step()
                    game.until(lambda g: g.info.state == 10000, limit=2000)
                    self.assertEqual(game.be(0x4d0354), 0)
                    self.assertEqual(game.be(0x4d0326), 3)
                else:
                    game.until(lambda g: g.state == (8, 1))
                    game.step(frames=130)
                    game.step(A)
                    game.step()
                    game.until(lambda g: g.info.state == 1, limit=1200)

    def test_native_save_reload_and_invalid_save(self):
        with Game() as game:
            game.new_game(5)
            game.write_be(0x4d0326, 8)
            game.write_be(0x4d034c, 3)
            game.write(0x610720, 123450)
            game.write_be(0x4d0354, 4)
            game.write_be(0x4d0356, 5)
            game.write_be(0x4d0350, 2)
            game.call(0x48a638)
        save = Path(self.directory.name) / "pcsonic.sav"
        self.assertEqual(save.stat().st_size, 835)
        with Game() as game:
            game.until(lambda g: g.state == (1, 7))
            game.step(frames=130)
            game.step(DOWN)
            game.step()
            self.assertEqual(game.read(0x779704), 1)
            game.step(A)
            game.step()
            game.until(lambda g: g.info.state == 10000)
            self.assertEqual(game.be(0x4d0324), 5)
            self.assertEqual(game.be(0x4d0326), 8)
            self.assertEqual(game.be(0x4d034c), 3)
            self.assertEqual(game.read(0x610720), 123450)
        damaged = bytearray(save.read_bytes())
        damaged[0] ^= 1
        save.write_bytes(damaged)
        with Game() as game:
            game.until(lambda g: g.state == (1, 7))
            game.step(frames=130)
            game.step(DOWN)
            game.step()
            game.step(A)
            game.step()
            game.until(lambda g: g.info.state == 10000)
            self.assertEqual(game.be(0x4d0324), 1)
            self.assertEqual(game.be(0x4d034c), 0)

    def test_final_boss_and_ending_gate(self):
        for gems, expected in ((0, 1002), (7, 10000)):
            with self.subTest(gems=gems), Game() as game:
                game.until(lambda g: g.state == (1, 6))
                game.step(frames=120)
                game.write(0x4bdf00, 22)
                game.step(START)
                game.step()
                game.until(lambda g: g.info.state == 4)
                game.write_be(0x4d034c, gems)
                game.until(lambda g: g.info.state in (10000, 1002))
                self.assertEqual(game.info.state, expected)
                if gems == 7:
                    game.step(frames=180)
                    self.assertEqual(game.read(0x5eaaec, 2), 0x8a)
                    self.assertEqual(game.info.music_track, 20)

    def test_movies_and_both_credit_sequences(self):
        for state in (1000, 1001, 1002):
            with self.subTest(state=state), Game() as game:
                game.until(lambda g: g.state == (1, 6))
                game.events.clear()
                force_state(game, state)
                game.step(frames=5)
                self.assertTrue(any(e[1:3] == (3, 1) for e in game.events))
                if state != 1000:
                    game.until(lambda g: g.info.state == (1004 if state == 1001 else 1005))
                    game.step(frames=100)
                    self.assertEqual(game.info.music_track, 25)
                game.until(lambda g: g.info.state == 1, limit=15000)

    def test_exit_menu(self):
        with Game() as game:
            game.until(lambda g: g.state == (1, 6))
            game.step(frames=130)
            game.step(DOWN)
            game.step()
            self.assertEqual(game.read(0x779704), 2)
            game.step(A)
            self.assertTrue(game.quit_requested)


if __name__ == "__main__":
    unittest.main(verbosity=2)
