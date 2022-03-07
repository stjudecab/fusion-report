""" Sync module """
import os
from zipfile import ZipFile
import time
import pandas as pd

from argparse import Namespace
from multiprocessing import Manager, Pool, Process
from typing import List

from fusion_report.common.exceptions.download import DownloadException
from fusion_report.common.logger import Logger
from fusion_report.common.net import Net
from fusion_report.data.fusiongdb import FusionGDB
from fusion_report.data.fusiongdb2 import FusionGDB2
from fusion_report.data.mitelman import MitelmanDB
from fusion_report.settings import Settings


class Sync:

    def __init__(self, params: Namespace):
        self.cosmic_token = Net.get_cosmic_token(params)

        # making sure output directory exists
        if not os.path.exists(params.output):
            os.makedirs(params.output, 0o755)

        os.chdir(params.output)
        return_err: List[str] = Manager().list()

        processes = [
            Process(name=Settings.FUSIONGDB['NAME'], target=self.get_fusiongdb, args=(return_err,)),
            Process(name=Settings.MITELMAN['NAME'], target=self.get_mitelman, args=(return_err,)),
            Process(name=Settings.COSMIC['NAME'], target=Net.get_cosmic, args=(self.cosmic_token, return_err,)),
            Process(name=Settings.FUSIONGDB2['NAME'], target=self.get_fusiongdb2, args=(return_err,))
        ]

        for process in processes:
            process.start()

        for process in processes:
            process.join()

        if len(return_err) > 0:
            raise DownloadException(return_err)

        time.sleep(1)
        Logger(__name__).info('Cleaning up the mess')
        Net.clean()

    def get_fusiongdb(self, return_err: List[str]) -> None:
        """Method for download FusionGDB database."""

        pool_params = [
            (f'{Settings.FUSIONGDB["HOSTNAME"]}/{x}', True) for x in Settings.FUSIONGDB["FILES"]
        ]
        pool = Pool(Settings.THREAD_NUM)
        pool.starmap(Net.get_large_file, pool_params)
        pool.close()
        pool.join()
        db = FusionGDB('.')
        db.setup(Settings.FUSIONGDB['FILES'], delimiter='\t', skip_header=False)

    def get_fusiongdb2(self, return_err: List[str]) -> None:
        """Method for download FusionGDB2 database."""
        try:
            url: str = f'{Settings.FUSIONGDB2["HOSTNAME"]}/{Settings.FUSIONGDB2["FILE"]}'
            Net.get_large_file(url)
            file : str = f'{Settings.FUSIONGDB2["FILE"]}'
            df = pd.read_excel(file)
            file_csv = 'fusionGDB2.csv'
            df.to_csv(file_csv, header=True, index=False, sep = '\t')

            db = FusionGDB2('.')
            print(file_csv)
            db.setup([file_csv], delimiter='\t', skip_header=True)

        except DownloadException as ex:
            return_err.append(f'FusionGDB2: {ex}')


    def get_mitelman(self, return_err: List[str]) -> None:
        """Method for download Mitelman database."""
        try:
            url: str = f'{Settings.MITELMAN["HOSTNAME"]}/{Settings.MITELMAN["FILE"]}'
            Net.get_large_file(url)
            with ZipFile(Settings.MITELMAN['FILE'], 'r') as archive:
                files = [ x for x in archive.namelist() if "mitelman_db/MBCA.TXT.DATA" in x ]
                archive.extractall()


            db = MitelmanDB('.')
            db.setup(files, delimiter='\t', skip_header=False, encoding='ISO-8859-1')
        except DownloadException as ex:
            return_err.append(f'Mitelman: {ex}')
