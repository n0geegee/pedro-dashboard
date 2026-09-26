"""Behavioral contracts for persistent, exactly-once photo rounds."""
from __future__ import annotations
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]

def load_probe():
    spec=importlib.util.spec_from_file_location('photos_cycle_probe',ROOT/'scripts/refresh-photos-slideshow.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class PhotoCycleTests(unittest.TestCase):
    def test_277_once_despite_refreshes_and_fresh_process_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            state=root/'app/state'
            state.mkdir(parents=True)
            images=[{'public_url':f'/static/cache/photos/photo-{i}.webp'} for i in range(277)]
            manifest={'album_url':'https://example.test/album','count':277,'images':images}
            rng=random.Random(17)
            outputs=[]
            for step in range(277):
                # New module instance simulates each real short-lived rotator process.
                module=load_probe()
                if step%60==0:
                    rng.shuffle(manifest['images'])
                (state/'photos_manifest.json').write_text(json.dumps(manifest))
                with patch.object(module,'project_root',return_value=root), patch.object(module,'resolve_state_dir',return_value=state), patch.object(module.random,'SystemRandom',return_value=rng), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(module._main_locked(allow_manifest_refresh=False),0)
                media=json.loads((state/'media.json').read_text())
                outputs.append(media['data']['slideshow']['image_url'])
            self.assertEqual(len(set(outputs)),277,'album refresh repeated photos before all 277 appeared')

    def test_failed_commit_keeps_last_slide_and_unconsumed_queue(self):
        module=load_probe()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            state=root/'app/state'
            state.mkdir(parents=True)
            manifest={'album_url':'a','images':[{'public_url':f'/static/cache/photos/{i}.webp'} for i in range(3)]}
            (state/'photos_manifest.json').write_text(json.dumps(manifest))
            with patch.object(module,'project_root',return_value=root), patch.object(module,'resolve_state_dir',return_value=state), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module._main_locked(allow_manifest_refresh=False),0)
                before=(state/'media.json').read_bytes()
                original=module.atomic_write
                calls=[]
                def fail_once(path,payload):
                    calls.append(path)
                    if len(calls)==1:
                        raise OSError('injected failed commit')
                    return original(path,payload)
                with patch.object(module,'atomic_write',side_effect=fail_once):
                    rc=module._main_locked(allow_manifest_refresh=False)
                self.assertNotEqual(rc,0,'a failed commit must not be reported as success')
                self.assertEqual((state/'media.json').read_bytes(),before)

    def test_inventory_refresh_does_not_shuffle_playback(self):
        module=load_probe()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            urls=['https://example.test/a','https://example.test/b']
            with patch.object(module,'fetch_album_urls',return_value=urls), patch.object(module,'download_if_needed',return_value=False), patch.object(module,'_measure_image',return_value={'width':1,'height':1,'orientation':'square'}), patch.object(module,'shuffle_manifest_order',side_effect=AssertionError('inventory refresh must not shuffle playback')):
                result=module.cache_album('album',root/'cache',root/'manifest.json',0)
            self.assertEqual([i['source_url'] for i in result['images']],urls)

    def test_three_full_rounds_across_ten_random_seeds(self):
        module=load_probe()
        for seed in range(10):
            rng=random.Random(seed)
            images=[{'public_url':f'/static/cache/photos/{i}.webp'} for i in range(277)]
            manifest={'album_url':'album','images':images}
            saved=None
            last=None
            rounds=[]
            with patch.object(module.random,'SystemRandom',return_value=rng):
                for round_number in range(1,4):
                    shown=[]
                    for position in range(1,278):
                        if position%13==0:
                            rng.shuffle(images)
                        current,image,saved=module.pick_cycle_image(manifest,saved,last)
                        self.assertEqual(current,position)
                        self.assertEqual(saved['round'],round_number)
                        self.assertNotEqual(image['public_url'],last)
                        last=image['public_url']
                        shown.append(last)
                    self.assertEqual(len(set(shown)),277)
                    self.assertEqual(set(shown),{i['public_url'] for i in images})
                    rounds.append(shown)
            self.assertNotEqual(rounds[0],rounds[1])

    def test_additions_wait_until_next_round_deletions_skip(self):
        module=load_probe()
        images=[{'public_url':s} for s in ['a','b','c','d']]
        manifest={'album_url':'album','images':images}
        with patch.object(module,'shuffle_manifest_order',side_effect=lambda x:x):
            _,image,saved=module.pick_cycle_image(manifest,None,None)
            self.assertEqual(image['public_url'],'a')
            manifest['images']=[images[0],images[2],images[3],{'public_url':'new'}]
            current,image,saved=module.pick_cycle_image(manifest,saved,'a')
            self.assertEqual((current,image['public_url'],saved['round']),(2,'c',1))
            _,image,saved=module.pick_cycle_image(manifest,saved,'c')
            self.assertEqual(image['public_url'],'d')
            self.assertNotIn('new',saved['queue'])
            _,image,saved=module.pick_cycle_image(manifest,saved,'d')
            self.assertEqual(saved['round'],2)
            self.assertEqual(set(saved['queue']),{'a','c','d','new'})

    def test_single_photo_duplicate_inventory_and_album_change(self):
        module=load_probe()
        manifest={'album_url':'one','images':[{'public_url':'a'},{'public_url':'a'}]}
        _,_,saved=module.pick_cycle_image(manifest,None,None)
        current,image,saved=module.pick_cycle_image(manifest,saved,'a')
        self.assertEqual((current,image['public_url'],saved['round']),(1,'a',2))
        self.assertEqual(saved['queue'],['a'])
        manifest={'album_url':'two','images':[{'public_url':'b'},{'public_url':'c'}]}
        current,_,saved=module.pick_cycle_image(manifest,saved,'a')
        self.assertEqual((current,saved['round']),(1,1))
        self.assertEqual(set(saved['queue']),{'b','c'})
        with self.assertRaisesRegex(RuntimeError,'manifest_has_no_images'):
            module.pick_cycle_image({'images':[]},saved,None)

    def test_corrupt_saved_cycle_fails_without_reset(self):
        module=load_probe()
        manifest={'album_url':'album','images':[{'public_url':'a'},{'public_url':'b'}]}
        _,_,valid=module.pick_cycle_image(manifest,None,None)
        for changes in [{'queue':['a','a']},{'position':-1},{'position':True},{'position':3},{'schema_version':2},{'round':0}]:
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(RuntimeError,'invalid_photo_cycle'):
                    module.pick_cycle_image(manifest,{**valid,**changes},None)

    def test_cycle_survives_polsat_write_and_is_not_sent_by_api(self):
        from app import server
        module=load_probe()
        spec=importlib.util.spec_from_file_location('polsat_cycle_test',ROOT/'scripts/refresh-polsat-status.py')
        polsat=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(polsat)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            state=root/'app/state'
            state.mkdir(parents=True)
            (state/'photos_manifest.json').write_text(json.dumps({'album_url':'album','images':[{'public_url':'a'},{'public_url':'b'}]}))
            with patch.object(module,'project_root',return_value=root), patch.object(module,'resolve_state_dir',return_value=state), contextlib.redirect_stdout(io.StringIO()):
                module._main_locked(allow_manifest_refresh=False)
                before=json.loads((state/'media.json').read_text())
                with patch.dict('os.environ',{'PEDRO_PHOTOS_LOCK_FILE':str(root/'media.lock')}), patch.object(polsat,'polsat_window_running',return_value=False):
                    self.assertEqual(polsat.main(['--out',str(state)]),0)
                after=json.loads((state/'media.json').read_text())
                self.assertEqual(before['_photos_cycle'],after['_photos_cycle'])
                with patch.object(server,'STATE_DIR',state):
                    public=server.load_media_payload()
                    self.assertNotIn('_photos_cycle',json.dumps(public))
                    self.assertNotIn('"queue"',json.dumps(public))
                module._main_locked(allow_manifest_refresh=False)
                final=json.loads((state/'media.json').read_text())
                self.assertEqual(final['_photos_cycle']['position'],2)
                self.assertEqual(final['data']['transmission'],after['data']['transmission'])

    def test_native_cli_restart_continues_saved_round(self):
        import os
        import shutil
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            state=root/'app/state'
            state.mkdir(parents=True)
            (root/'scripts').mkdir()
            for name in ['refresh-photos-slideshow.py','_probe_common.py']:
                shutil.copy2(ROOT/'scripts'/name,root/'scripts'/name)
            images=[{'public_url':f'/static/cache/photos/{i}.webp'} for i in range(12)]
            (state/'photos_manifest.json').write_text(json.dumps({'album_url':'album','images':images}))
            outputs=[]
            for _ in images:
                result=subprocess.run([sys.executable,'-B',str(root/'scripts/refresh-photos-slideshow.py'),'--no-manifest-refresh'],env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PEDRO_PHOTOS_LOCK_FILE':str(root/'media.lock')},capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr)
                outputs.append(json.loads((state/'media.json').read_text())['data']['slideshow']['image_url'])
            self.assertEqual(len(set(outputs)),len(images))

if __name__=='__main__':
    unittest.main(verbosity=2)
