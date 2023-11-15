from portfolio.models import Transactions
from .TransactionsFromFile import TransactionsFromFile
from datetime import date as dt
from datetime import datetime
import numpy as np

class DashboardChartsProcessing(TransactionsFromFile):
    def __init__(self, user, ticker=None, subtract_dividends_from_contribution: str='N'):
        super().__init__()
        self.user = user
        self.ticker = ticker.upper() if ticker else None
        self.subtract_dividends_from_contribution = subtract_dividends_from_contribution.upper()

        self.transactions_list = self._get_transactions_list()

        if not self.transactions_list:
            raise ValueError('No data')

        self.tickers_list = self.extract_tickers_list(self.transactions_list)
        self.portfolio_balance = self.calculate_portfolio_balance_and_asset_history(self.transactions_list, self.tickers_list) # -> portfolio e asset_history
        self.portfolio = self.portfolio_balance[0] # Index 0 -> somente portfolio
        self.asset_history = self.portfolio_balance[1] # Index 1 -> somente asset_history
        self.first_transaction_date = self._get_first_transaction_date()
        self.interval = self._get_interval()
        self.history_data = self.load_history_data_of_tickers_list(list_of_tickers=self.tickers_list, initial_date=self.first_transaction_date, interval=self.interval)

        self.individual_performance_data = None # Dados de performance de cada ativo individualmente
        self.performance_data = None # Dados de performance consolidados (todos os ativos do portfolio)
    
    def _get_interval(self):
        time_elapsed = dt.today() - self.first_transaction_date
        if time_elapsed.days < 60:
            return '1d'
        elif time_elapsed.days < 180:
            return '1wk'
        else:
            return '1mo'

    def _get_transactions_list(self):
        if self.ticker is None:
            result = Transactions.objects.filter(portfolio__user=self.user)
        else:
            result = Transactions.objects.filter(portfolio__user=self.user, ticker=self.ticker)
        list_result = list(result.values())
        return self.list_of_dicts_order_by(list_result, ['date', 'ticker', 'operation'])
    
    def _get_first_transaction_date(self):
        result = min(self.transactions_list, key=lambda x: x['date'])
        return result['date']

    def _get_values_in_a_date(self, date, asset_history):
        
        # Classifica a lista de dicionários com base na data
        asset_history.sort(key=lambda x: x["date"])

        # Inicialize a quantidade com 0 (caso a data de entrada seja anterior à primeira data na lista)
        values = {'quantity': 0, 'average_price': 0.0}

        # Itera sobre os dicionários para encontrar a quantidade correspondente à data de entrada
        for data in asset_history:
            if data["date"] <= date:
                values['quantity'] = data["quantity"]
                values['average_price'] = data['average_price']
            else:
                break

        return values

    def _format_date(self, date):
        if isinstance(date, dt):
            return dt.strftime(date, '%d/%m/%Y')
        if isinstance(date, str):
            return datetime.strptime(date, '%d/%m/%Y').date()

    def _calculate_contribution_equity_dividends(self):
        # Cria um dicionário que conterá o histórico de data, aportes acumulados, patrimônio e dividendos acumulados ao longo do tempo. Tudo isso de cada ativo:
        individual_performance_data = {
            ticker: {
                'date': [],
                'contribution': [],
                'equity': [],
                'dividends': [],    
            } for ticker in self.history_data.keys()
        }
        
        # Percorre a lista de tickers
        for ticker in self.tickers_list:
            acum_dividends = 0
            # Percorre os dados históricos de cada ticker:
            for data in self.history_data[ticker]:

                # Se não houver dados na data especificada, preencha os dados com a data específica e os valores = 0.0
                '''Se houver dados:
                    primeiro extrai a quantidade e o preço médio do ticker na data do dado atual;
                    depois obtem os valores de data, aportes (multiplicando o preço médio pela qtdade),
                    de patrimônio (multiplicando o fechamento pela quantidade) e de dividendos (multipli
                    cando o valor do dividendo pela quantidade - os valores de dividendos são acumulatórios)
                  '''
                date = self._format_date(data['date'])
                if np.isnan(data['close']):
                    acum_contribution = 0.0
                    equity = 0.0
                    acum_dividends = 0.0
                else:
                    values = self._get_values_in_a_date(data['date'], self.asset_history[ticker])
                    acum_contribution = values['quantity'] * values['average_price']
                    equity = values['quantity'] * data['close']
                    acum_dividends = acum_dividends + values['quantity'] * data['dividends']
                    
                    # Subtrai os dividendos recebidos do valor dos aportes:
                    if self.subtract_dividends_from_contribution == 'Y':
                        acum_contribution = acum_contribution - acum_dividends

                # Atualiza o dicionário com o ticker e os dados obtidos acima:
                individual_performance_data[ticker]['date'].append(date)
                individual_performance_data[ticker]['contribution'].append(acum_contribution)
                individual_performance_data[ticker]['equity'].append(equity)
                individual_performance_data[ticker]['dividends'].append(acum_dividends)

                '''Se houver splits ou grupamentos, atualiza o valor da lista de patrimonios obtidos até o momento,
                porque o preço de fechamento (que vem do yfinance) está ajustado e não reflete o preço real da época:'''
                if data['split_groupment'] > 0.0:
                    for i, equity_value in enumerate(individual_performance_data[ticker]['equity']):
                        individual_performance_data[ticker]['equity'][i] *= data['split_groupment']
        return individual_performance_data

    def _consolidate_performance_data(self, individual_performance_data):
        # Cria um dicionário que conterá os dados consolidados de todos os ativos:
        final_performance_data = {
            'date': [],
            'contribution': [],
            'equity': [],
            'dividends': [],    
        }

        # Inicializa o dicionário com todas as datas do histórico e com os valores correspondentes zerados:
        for key, values in individual_performance_data.items():
            final_performance_data['date'] = values['date']
            final_performance_data['contribution'] = [0.0] * len(values['contribution'])
            final_performance_data['equity'] = [0.0] * len(values['equity'])
            final_performance_data['dividends'] = [0.0] * len(values['dividends'])
        
        # Consolida os valores da lista somando por data
        for _, values in individual_performance_data.items():
            for key in ['contribution', 'equity', 'dividends']:
                final_performance_data[key] = list(np.round(np.add(final_performance_data[key], values[key]), 2))
                # final_performance_data[key] = [round(x + y, 2) for x, y in zip(final_performance_data[key], values[key])]
        return final_performance_data

    def get_performance_chart_data(self):

        individual_performance_data = self._calculate_contribution_equity_dividends()
        self.individual_performance_data = individual_performance_data

        final_performance_data = self._consolidate_performance_data(individual_performance_data)

        self.performance_data = final_performance_data
        return final_performance_data

    def get_category_data(self):
        categories_set = {asset['sort_of'] for asset in self.portfolio.values() if asset['sort_of'] != 'Split/Agrup'}
        category_data = []

        # Percorre a lista de categorias
        for category in categories_set:
            value = 0
            # Percorre todos os itens do portfolio:
            for ticker, asset in self.portfolio.items():
                # Se a categoria do item do portfolio for a mesma categoria do loop inicial
                # inclui o valor do patrimonio atual daquele ativo
                if asset['sort_of'] == category:
                    value += asset['quantity'] * self.history_data[ticker][-1]['close'] # Obtem o último fechamento do histórico de preços
            
            category_data.append(
                {
                    'value': round(value, 2),
                    'name': category,
                }
            )
        return self.list_of_dicts_order_by(category_data, ['values',], reversed_output=True)

    def get_asset_data(self):
        asset_data = []
        for ticker, asset in self.portfolio.items():
            asset_data.append(
                {
                    'name': ticker,
                    'value': round(asset['quantity'] * self.history_data[ticker][-1]['close'], 2)
                }
            )
        return self.list_of_dicts_order_by(asset_data, ['value',], reversed_output=True)

    def _calculate_change(self, value_in_period, initial_value):
        if initial_value == 0:
            return 0.0
        else:
            return value_in_period / initial_value

    def get_cards_data(self):
        # Se os dados de performance ainda não foram calculados, executa o cálculo:
        if not self.performance_data:
            self.get_performance_chart_data()

        equity_data: dict = {}
        contribution_data : dict = {}
        dividends_data: dict = {}

        time_periods = {
            '1d': ['0d', '1d', '2d', '3d', '4d', '5d', '6d'],
            '1wk': ['0sem', '1sem', '2sem', '3sem', '4sem', '5sem', '6sem'],
            '1mo': ['0m', '1m', '2m', '3m', '4m', '5m', '6m'],
        }
        periods = time_periods[self.interval]
        
        iter_range = len(periods)
        for _ in range(iter_range):
            if len(self.performance_data['date']) >= len(periods):
                for i, period in enumerate(periods):
                    equity_data[period] = self.performance_data['equity'][-(i+1)]
                    contribution_data[period] = self.performance_data['contribution'][-(i+1)]
                    dividends_data[period] = self.performance_data['dividends'][-(i+1)]
                break
            else:
                periods.pop()
        
        # Cálculos relacionados aos Aportes:
        current_contribution = contribution_data[periods[0]]
        initial_contribution = contribution_data[periods[-1]]
        contribution_in_period = current_contribution - initial_contribution
        contribution_change = self._calculate_change(contribution_in_period, initial_contribution)
        contribution = {'value': current_contribution, 'period': periods[-1], 'change': contribution_change}

        # Cálculo relacionado ao Patrimônio
        current_equity = equity_data[periods[0]]
        initial_equity = equity_data[periods[-1]]
        result_in_period = current_equity - initial_equity
        equity_change = self._calculate_change(result_in_period, initial_equity)
        equity = {'value': current_equity, 'period': periods[-1], 'change': equity_change}

        # Cálculos relacionados aos Resultados (em porcentagem):
        current_result = current_equity - current_contribution
        current_result_percent = self._calculate_change(current_result, current_contribution)
        initial_result = initial_equity - initial_contribution
        initial_result_percent = self._calculate_change(initial_result, initial_contribution)
        result_change = current_result_percent - initial_result_percent
        result = {'value': current_result_percent, 'period': periods[-1], 'change': result_change}

        # Cálculo relacionados ao Yield on Cost:
        current_dividends = dividends_data[periods[0]]
        initial_dividends = dividends_data[periods[-1]]
        current_yield_on_cost = self._calculate_change(current_dividends, current_contribution)
        initial_yield_on_cost = self._calculate_change(initial_dividends, initial_contribution)
        yield_on_cost_change = current_yield_on_cost - initial_yield_on_cost
        yield_on_coast = {'value': current_yield_on_cost, 'period': periods[-1], 'change': yield_on_cost_change}

        yield_ = round(current_equity - current_contribution, 2)

        cards_data = {
            'contribution': contribution,
            'equity': equity,
            'result': result,
            'yield_on_cost': yield_on_coast,
            'yield': yield_,
        }
        
        return cards_data

    def get_contributions_over_time(self, show_months_without_contribution=False):
        contribution_over_time:dict = {}
        
        # Percorre a lista de transações. 
        for transaction in self.transactions_list:
            # Se a operação não for de compra, pula para a próxima
            if transaction['operation'] != 'C':
                continue
            # Obtêm o mes/ano da operação. Se o mes/ano já se encontrar na variável 'contribution_over_time' adiciona o valor total da transação
            # Se o mes/ano não for encontrado na referida variável, cria um novo par key/value
            month_year = f"{transaction['date'].month}/{transaction['date'].year}"
            if contribution_over_time.get(month_year):
                contribution_over_time[month_year] += transaction['quantity'] * transaction['unit_price']
            else:
                contribution_over_time[month_year] = transaction['quantity'] * transaction['unit_price']

        # Se verdadeiro, prossegue para adicionar os meses com zero contribuição.
        # Se falso, retorna o resultado
        if not show_months_without_contribution:
            return contribution_over_time

        # Caso ainda não tenha sido calculada a performance, calcula
        if self.performance_data is None:
            self.get_performance_chart_data()

        # Percorre as datas dos dados de performance
        for date_ in self.performance_data['date']:
            # Obtêm o mes/ano destas datas
            formatted_date = self._format_date(date_)
            month_year = f"{formatted_date.month}/{formatted_date.year}"
            # Se o mes/ano obtido não for encontrado nos dados de aportes calculados acima, significa que não houve aportes no referido mes/ano
            # Então adiciona a data com o valor de aporte = 0.0 à variável 'contribution_over_time'
            if not contribution_over_time.get(month_year):
                contribution_over_time[month_year] = 0.0

        # Extrai a lista de mes/ano ordenada do mais velho para a mais novo
        def extract_month_year(key):
            return datetime.strptime(key, '%m/%Y')
        list_of_months_years = sorted(contribution_over_time.keys(), key=extract_month_year)
        
        final_contribution_over_time = {
            'date': [],
            'contribution': [],
        }

        # Percorre a lista de mes/ano e adiciona um por um, na chave 'date' e na chave 'contribution'
        for month_year in list_of_months_years:
            final_contribution_over_time['date'].append(month_year)
            final_contribution_over_time['contribution'].append(contribution_over_time.get(month_year))
        
        return final_contribution_over_time

    def get_asset_variation_chart_data(self):
        # Cria um dicionário contendo todos os tickers com valores de variação = 0.0:
        asset_variation_data = {
            'ticker': [],
            'variation': [],
        }
        
        #Percorre os dados de performance individual de cada ativo:
        for ticker, data in self.individual_performance_data.items():
            equity = data['equity'][-1] # Obtêm o valor do patrimônio atual do ativo (último item da lista)
            contribution = data['contribution'][-1] # Obtêm o valor acumulado de aportes do ativo (último item da lista)
            income = equity - contribution # Calcula o lucro ou prejuízo do período
            variation = self._calculate_change(income, contribution) # Calcula a porcentagem do lucro ou prejuízo
            asset_variation_data['ticker'].append(ticker)
            asset_variation_data['variation'].append(round(variation * 100, 2))
        
        return asset_variation_data

