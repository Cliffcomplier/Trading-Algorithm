# https://github.com/deribit/deribit-api-clients/tree/master/python
import datetime
from deribit_api import RestClient
import re
import calendar
import time
import pandas as pd
import json
from pprint import pprint
from twilio.rest import Client
with open('.\Tokens.json', 'r') as f:
    Tokens = json.load( f)


def sms_notification(txt):
    # Your Account SID from twilio.com/console
    account_sid = "ACf78f82c3dbf7ff20d50162500c5779d6"
    # Your Auth Token from twilio.com/console
    auth_token  = "9c351c76873b6550d73348a173d16795"

    client = Client(account_sid, auth_token)

    message = client.messages.create(
        to="+8615393106726",
        from_="+12055519388",
        body=txt)



class trading:
# Real Trading
    def __init__(self,client_id = Tokens['Deribit']['Read_and_Write']['id'],client_secret = Tokens['Deribit']['Read_and_Write']['secret']):
        # Login read only account
        self.MyAccount = RestClient(client_id,client_secret)
        self.Fee = {
            'Future':{
                        'Market':0.00075,'Limit':-0.0025
                    },
            'Option':0.0004
        }
        self.Max_Order_Num = 3
        self.Trading_Frequency = 1
    def post_order(self,Instrument,Short_or_Long,Post_Size):
        def get_Post_Dist(Orderbook,Bid_or_Ask,Order_Num,Post_Size):
            Top_Order = [Orderbook[Bid_or_Ask][i]['quantity'] for i in range(Order_Num)]
            Order_Weight = [Top_Order[i]*Post_Size/sum(Top_Order) for i in range(Order_Num)]
            # If the order weight is smaller than 0.1 then add it to 0.1
            Order_Weight = [round(w,1) for w in Order_Weight]
            Order_Weight[0] = Order_Weight[0] + (Post_Size - sum(Order_Weight))
            # Transfer it as order dictionary
            Post_Dist = [{'price':Orderbook[Bid_or_Ask][i]['price'],'size':Order_Weight[i]} for i in range(Order_Num)]
            return Post_Dist
        Orderbook = self.MyAccount.getorderbook(Instrument)
        # Post orders by weighted-size
        if Short_or_Long == 'Short':
            Bid_or_Ask = 'asks'
        elif Short_or_Long == 'Long':
            Bid_or_Ask = 'bids'
        Order_Num = min(int(Post_Size/0.1),min(self.Max_Order_Num,len(Orderbook[Bid_or_Ask]))) # Total number of orders will be posted
        Post_Dist = [] # Store price and amount of each orders will be posted
        if Orderbook['bids'][min(2,len(Orderbook['bids']))]['cm']>Orderbook['asks'][min(2,len(Orderbook['bids']))]['cm']:
            # Bid pressure is larger than Ask pressure, then post order at the top orders of asks book
            Post_Dist = get_Post_Dist(Orderbook,Bid_or_Ask,Order_Num,Post_Size)
        else:
            # Bid pressure is smaller than Ask pressure, then post order above and at the orders of ask book
            if Orderbook['asks'][0]['price'] - Orderbook['bids'][0]['price']<0.001:
                Post_Dist = [{'price':Orderbook['bids'][0]['price'],'size':Post_Size}]

            else:
                First_Order = max(0.1,round(Post_Size/3,1))
                Post_Dist = [{'price':Orderbook['asks'][0]['price']-0.0005,'size':First_Order}]
                Post_Dist = Post_Dist + get_Post_Dist(Orderbook,Bid_or_Ask,Order_Num - 1,Post_Size - First_Order)

        Post_Dist = [{'price':Post_Dist[i]['price'],'size':round(Post_Dist[i]['size'],1)} for i in range(len(Post_Dist))]
        # Print the result
        print("There will be %d %s orders posted:"%(Order_Num,Short_or_Long.lower()))
        pprint(Post_Dist)
        Execute_or_Not = input('Post those orders? [y/n]')
        if Execute_or_Not == 'y':
            ###---Post Orders---###
            if Short_or_Long == 'Short':
                [self.MyAccount.sell(Instrument, p['size'], p['price'], False) for p in Post_Dist]
                for p in Post_Dist:
                    if p['size']!=0:
                        self.MyAccount.sell(Instrument, p['size'], p['price'], False)
                time.sleep(self.Trading_Frequency)
            elif Short_or_Long == 'Long':
                for p in Post_Dist:
                    if p['size']!=0:
                        self.MyAccount.buy(Instrument, p['size'], p['price'], False)
                time.sleep(self.Trading_Frequency)
            else:
                print('Error occurs')
                return False
            ###------###
            return True
        else:
            return False
    def get_current_btc_postition(self,Instrument):
        if len(self.MyAccount.positions())!=0:
            if sum([p['instrument'] == 'BTC-PERPETUAL' for p in self.MyAccount.positions()])!= 0: # list is not empty
                Perpetual_Position = self.MyAccount.positions()\
                    [\
                        [p['instrument'] == 'BTC-PERPETUAL' for p in self.MyAccount.positions()].index(True)\
                    ]['sizeBtc']
            else:
                Perpetual_Position = 0
            if sum([p['instrument'] == Instrument for p in self.MyAccount.positions()]) != 0: # list is not empty
                Option_Position = self.MyAccount.positions()\
                    [\
                        [p['instrument'] == Instrument for p in self.MyAccount.positions()].index(True)\
                    ]['size']
            else:
                Option_Position = 0
        else:
            Perpetual_Position = 0
            Option_Position = 0
        return Perpetual_Position,Option_Position
    def hedge(self,Instrument,Strike_Price):
        BTC_Price = float(self.MyAccount.index()['btc'])
        Perpetual_Position,Option_Position = self.get_current_btc_postition(Instrument)
        # Hedge current risk exposure
        while (BTC_Price < Strike_Price) and (Perpetual_Position> Option_Position): # Hedging
            sms_notification('Hedging Start.')
            Execute_or_Not = input('Cancel all orders?[y/n]')
            if Execute_or_Not == 'y':
                self.MyAccount.cancelall()
            else:
                return False
            Orderbook = self.MyAccount.getorderbook('BTC-PERPETUAL')
            Post_Size = abs(float(Perpetual_Position - Option_Position))
            Top_Order_Size = Orderbook['bids'][0]['quantity']/Orderbook['bids'][0]['price'] # Top_Order_Size is counted as BTC
            print("There will be %lf perpetual shorted at %lf"%(min(Post_Size,Top_Order_Size),\
                                                                    Orderbook['bids'][0]['price']))
            sms_notification("There will be %lf perpetual shorted at %lf [y/n]"%(min(Post_Size,Top_Order_Size),\
                                                                    Orderbook['bids'][0]['price']))
            Execute_or_Not = input('Post those orders? [y/n]')
            if Execute_or_Not == 'y':
                ###------ Post Order ------###
                Sell_Size = int(min(\
                                    Post_Size,\
                                    Top_Order_Size\
                                   )*Orderbook['bids'][0]['price']/10\
                               )
                if Sell_Size >=1:
                    self.MyAccount.sell('BTC-PERPETUAL',Sell_Size , Orderbook['bids'][0]['price'], False)
                    time.sleep(self.Trading_Frequency)
                else:
                    print("Sell Size is smaller than the minimal requirement.")
                ###------ Post Order Completed ------###
            else:
                print("Trading Stop")
                return False
            BTC_Price = self.MyAccount.index()['btc']
            Perpetual_Position,Option_Position = self.get_current_btc_postition(Instrument)
        # Clear the previous perpetual position
        Orderbook = self.MyAccount.getorderbook('BTC-PERPETUAL')
        while (int(Orderbook['bids'][0]['price']*Perpetual_Position/10-1e-3)<=-1) and (BTC_Price>=Strike_Price): # Closing position
            Execute_or_Not = input('Cancel all orders?[y/n]')
            if Execute_or_Not == 'y':
                self.MyAccount.cancelall()
            else:
                return False
            Perpetual_Position,Option_Position = self.get_current_btc_postition(Instrument)
            BTC_Price = self.MyAccount.index()['btc']
            if Perpetual_Position>0:
                # Short Perpetual
                Orderbook = self.MyAccount.getorderbook('BTC-PERPETUAL')
                Post_Size = min(abs(float(Perpetual_Position)),Orderbook['bids'][0]['quantity']/Orderbook['bids'][0]['price'])
                print("There will be %lf perpetual shorted at %lf[y/n]"%(Post_Size,Orderbook['bids'][0]['price']))
                sms_notification("There will be %lf perpetual shorted at %lf"%(Post_Size,Orderbook['bids'][0]['price']))
                Execute_or_Not = input('Post those orders? [y/n]')
                if Execute_or_Not == 'y':
                    ###------ Post Order ------###
                    Sell_Size = int(Post_Size*Orderbook['bids'][0]['price']/10)
                    if Sell_Size >= 1:
                        self.MyAccount.sell('BTC-PERPETUAL', Sell_Size, Orderbook['bids'][0]['price'], False)
                        # Post_Size is counted as BTC, but sell perpetual is counted as 10 USD, so we do a bit transfer.
                        time.sleep(self.Trading_Frequency)
                    else:
                        print("Sell Size is smaller than the minimal requirement.")
                    ###------ Post Order Completed ------###
                else:
                    return False
            if Perpetual_Position<0:
                # Long Perpetual
                Orderbook = self.MyAccount.getorderbook('BTC-PERPETUAL')
                Post_Size = min(abs(float(Perpetual_Position)),Orderbook['asks'][0]['quantity']/Orderbook['asks'][0]['price'])
                print("There will be %lf perpetual longed at %lf"%(Post_Size,Orderbook['asks'][0]['price']))
                sms_notification("There will be %lf perpetual longed at %lf[y/n]"%(Post_Size,Orderbook['asks'][0]['price']))
                Execute_or_Not = input('Post those orders? [y/n]')
                if Execute_or_Not == 'y':
                    ###------ Post Order ------###
                    Buy_Size = int(Post_Size*Orderbook['asks'][0]['price']/10)
                    if Buy_Size >= 1:
                        self.MyAccount.buy('BTC-PERPETUAL', Buy_Size, Orderbook['asks'][0]['price'], False)
                        # Post_Size is counted as BTC, but sell perpetual is counted as 10 USD, so we do a bit transfer.
                        time.sleep(self.Trading_Frequency)
                    else:
                        print("Buy Size is smaller than the minimal requirement.")
                    ###------ Post Order Completed ------###
                else:
                    return False

        return True

    def short_option(self,Date,Year,Strike_Price,Contract_Type):
        Instrument = "BTC-%s%s-%s-%s"%(Date.upper(),Year,Strike_Price,Contract_Type.upper())
        Strike_Price = float(Strike_Price)
        # Compute margin and fee cost
        markPrice = self.MyAccount.getsummary(Instrument)['markPrice']
        btcPrice = self.MyAccount.index()['btc']
        MM_Option = max(0.075,0.075*markPrice)+markPrice # Maintianence margin
        IM_Option = max(max(0.15 - (btcPrice - float(Strike_Price))/btcPrice,0.1)+markPrice,MM_Option)# Initial margin
        size = 0.25
        IM_Future = 0.01+(0.005/100)*size
        Required_Balance = (IM_Option+self.Fee['Option'])*size + size*(IM_Future+self.Fee['Future']['Market'])
        Account = self.MyAccount.account()
        while Required_Balance<=Account['availableFunds']:
            print('Required Balance = %lf if size = %lf'%(Required_Balance,size))
            size += 0.05
            IM_Future = 0.01+(0.005/100)*size
            Required_Balance = (IM_Option+self.Fee['Option'])*size + size*(IM_Future+self.Fee['Future']['Market'])

        # Short Option
        Short_Size = float(input("Short Size:")) # Total position will be shorted
        pprint({\
                'availableFunds':self.MyAccount.account()['availableFunds']\
                ,'balance':self.MyAccount.account()['balance']\
                ,'equity':self.MyAccount.account()['equity']\
              ,'initialMargin':self.MyAccount.account()['initialMargin']\
              ,'maintenanceMargin':self.MyAccount.account()['maintenanceMargin']\
               })
        while Short_Size !=0:
            if len(self.MyAccount.positions()) !=0:
                Current_Size = self.MyAccount.positions()\
                [\
                    [p['instrument'] == Instrument for p in self.MyAccount.positions()].index(True)\
                ]['size']
            else:
                Current_Size = 0
            Short_Size = Short_Size - abs(float(Current_Size))
            print("Short Option: %lf"%Short_Size) # Print Short Size
            # Clear all open orders
            Execute_or_Not = input('Cancel all orders?[y/n]')
            if Execute_or_Not == 'y':
                self.MyAccount.cancelall()
            else:
                return False
            # Post new orders
            if not self.post_order(Instrument,'Short',Short_Size):
                print("Trading stop")
                pprint(self.MyAccount.account())
                return 0
            Continue_or_Not = input('Continue Short Options or Not [y/n]')
        # Hedge
        Mon = list(calendar.month_abbr).index(Date[(len(Date)-3):len(Date)][0].upper()+Date[(len(Date)-3):len(Date)][1:3].lower())
        Day = int(Date[0:(len(Date)-3)])
        settle_time = datetime.datetime(int("20%s"%Year),Mon,Day,16,0)
        while datetime.datetime.now() <=settle_time:
             if not self.hedge(Instrument,Strike_Price):
                print("Trading stop")
                pprint(self.MyAccount.account())
                return 0
        return 0
    def alert(self):
        BTC_Price = self.MyAccount.index()['btc']
        if BTC_Price<9125:
            sms_notification("Wake up! Price is out of bound")


# Enquiry Option type
trading().alert()
