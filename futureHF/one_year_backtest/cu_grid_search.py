from sys import path
path.append('/work/rqiao/HFdata')
from mewp.simulate.wrapper import PairAlgoWrapper
from mewp.simulate.runner import PairRunner
from mewp.math.simple import SimpleMoving
from mewp.util.clock import Clock
from mewp.data.order import OrderType
from mewp.reader.futuresqlite import SqliteReaderDce
from mewp.util.futures import get_day_db_path
from joblib import Parallel, delayed
import datetime
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import itertools
import pickle
import os
DATA_PATH = '/work/rqiao/HFdata/dockfuture'
market = 'shfe'

def get_contract_list(market, contract):
    return os.listdir(DATA_PATH + '/' + market + '/' + contract)

def get_position(contract, date, DATA_PATH):
    # create a dictionary, where date is the key
    try:
        reader = SqliteReaderDce(get_day_db_path(DATA_PATH, contract, date))
        raw = reader.read_tick()
        result = int(raw['Position'].tail(1))
    except Exception:
        result = 0
    return result

def get_best_pair(date, market, contract):
    #input a date(format: '2016-01-01'), return the best pair of contract
    cont_list = get_contract_list(market, contract)
    score = []
    for i, c in enumerate(cont_list):
        score.append(get_position(c, date, DATA_PATH))
    if sum(score) == 0:
        return 0
    max_idx = np.argmax(score)
    score[max_idx] = 0
    second_max_idx = np.argmax(score)
    return (cont_list[max_idx], cont_list[second_max_idx])

## Simple moving average pair trading
# Max position within 1
class TestAlgo(PairAlgoWrapper):

    # called when algo param is set
    def param_updated(self):
        # make sure parent updates its param
        super(TestAlgo, self).param_updated()
        #self.long_roll = SimpleMoving(size=self.param['rolling'])
        #self.short_roll = SimpleMoving(size=self.param['rolling'])
        self.sd_coef = self.param['sd_coef']
        self.block = self.param['block']

    def on_daystart(self, date, info_x, info_y):
        pass
        # recreate rolling at each day start
        self.long_roll = SimpleMoving(size=self.param['rolling'])
        self.short_roll = SimpleMoving(size=self.param['rolling'])

    def on_dayend(self, date, info_x, info_y):
        pos = self.position_y()
        # stop short position
        if pos == -1:
            self.long_y(y_qty = 1)
            return

        # stop long position
        if pos == 1:
            self.short_y(y_qty = 1)
            return

    def on_tick(self, multiple, contract, info):
        # skip if price_table doesnt have both, TODO fix this bug internally
        if len(self.price_table.table) < 2:
            return

        # get residuals and position
        long_res = self.pair.get_long_residual()
        short_res = self.pair.get_short_residual()
        pos = self.position_y()

        # action only when unblocked: bock size < rolling queue size
        if self.long_roll.queue.qsize() > self.block:
            # long when test long_res > roll.mean+sd_coef*roll.sd
            if self.long_roll.test_sigma(long_res, self.sd_coef):
                # only long when position is 0 or -1
                if pos <= 0:
                    self.long_y(y_qty=1)

            # short when test short_res > roll.mean+sd_coef*roll.sd
            elif self.short_roll.test_sigma(short_res, self.sd_coef):
                 # only short when position is 0 or 1
                if pos >= 0:
                    self.short_y(y_qty=1)
            else:
                pass

        # update rolling
        self.long_roll.add(long_res)
        self.short_roll.add(short_res)

def back_test(pair, date, param):
    algo = { 'class': TestAlgo }
    algo['param'] = {'x': pair[0],
                     'y': pair[1],
                     'a': 1,
                     'b': 0,
                     'rolling': param[0],
                     'sd_coef': param[1],
                     'block': 100,
                     }
    settings = { 'date': date,
                 'path': DATA_PATH,
                 'tickset': 'top',
                 'algo': algo}
    runner = PairRunner(settings)
    runner.run()
    account = runner.account
    history = account.history.to_dataframe(account.items)
    orders = account.orders.to_dataframe()
    pnl = np.asarray(history.pnl)[-1]
    return pnl, len(orders)

def run_simulation(param, date_list):
    total_pnl = 0
    total_order = 0
    for date in date_list:
        date_pair = get_best_pair(date,market, 'cu')
        if type(date_pair) != tuple:
            continue
        else:
            tpnl, torder = back_test(date_pair, date, param)
            total_pnl += tpnl
            total_order += torder
    return total_pnl, total_order

date_list = [str(x).split(' ')[0] for x in pd.date_range('2015-01-01','2016-03-31').tolist()]
roll_list = np.arange(1000, 8100, 1000)
sd_list = np.arange(1, 4.1, 0.2)
pars = list(itertools.product(roll_list, sd_list))
num_cores = 20
results = Parallel(n_jobs=num_cores)(delayed(run_simulation)(param, date_list) for param in pars)
result = pd.DataFrame({"rolling": [p[0] for p in pars],
                       "sd_coef": [p[1] for p in pars],
                       "PNL": [i for i, v in results],
                       "num_trades": [v for i, v in results]})
pickle.dump(result, open('cu_result.p','wb'))
