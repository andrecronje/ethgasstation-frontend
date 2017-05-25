import mysql.connector, sys
import pandas as pd
import numpy as np
import statsmodels.api as sm
import subprocess, json

cnx = mysql.connector.connect(user='ethgas', password='station', host='127.0.0.1', database='tx')
cursor = cnx.cursor()



startBlock = int(sys.argv[1])
endBlock = int(sys.argv[2])


# First Query to Determine Block TIme, and Estimate Miner Policies
query = ("SELECT * FROM speedo2 where blockNum>= %s and blockNum < %s")
cursor.execute(query, (startBlock, endBlock))
head = cursor.column_names

minerData = pd.DataFrame(cursor.fetchall())
minerData.columns = head
cursor.close()
cnx.close()

# Find Identical Main Blocks - Keep 1
minerData['mainIdents'] = minerData.duplicated(subset=['blockNum', 'main', 'uncsReported'])
minerData.loc[(minerData['mainIdents']==True) & (minerData['main']==0), 'mainIdents'] = False
minerData = minerData[minerData['mainIdents']==False]

#duplicated Uncles
minerData['uncleIdents'] = minerData.duplicated(subset=['blockHash'])
minerData = minerData[minerData['uncleIdents']==False]

print(minerData['uncle'].sum())
print(minerData['uncsReported'].sum())

#clean data

minerData['uncsReported'].fillna(value=0, inplace=True)
minerData.loc[minerData['uncle']==1, 'blockFee'] = 0
minerData = minerData.dropna(subset=['blockFee'])

#uncleReportingFees
minerData.loc[minerData['uncsReported']==1, 'includeFee' ] = .15625
minerData.loc[minerData['uncsReported']==2, 'includeFee'] = .3125
minerData.loc[minerData['uncsReported']==0, 'includeFee'] = 0

#define constants for all blocks

totalBlocks = len(minerData)
totalUncsReported = minerData['uncsReported'].sum()
totAvgGasUsed = minerData['gasUsed'].mean()
uncleRate = totalUncsReported/float(totalBlocks)
minerData['blockFee'] = minerData['blockFee']/1e9
totalIncludeFee = minerData['includeFee'].sum()
minerData['blockAward'] = 5 + minerData['includeFee'] + minerData['blockFee']
minerData['blockAwardwoFee'] = 5 + minerData['includeFee']
minerData['incDelay'] = minerData['includedBlockNum'] - minerData['blockNum']
minerData['mgasUsed'] = minerData['gasUsed']/1e6
avgMgasUsed = minerData['mgasUsed'].mean()
minMgasUsed = minerData['mgasUsed'].min()
maxMgasUsed = minerData['mgasUsed'].max()
minerData.loc[(minerData['gasUsed']==0) & (minerData['uncle']==True), 'emptyUncle'] = 1
minerData.loc[(minerData['gasUsed']==0) & (minerData['main']==True), 'emptyBlock'] = 1
minerData['emptyUncle'].fillna(0, inplace=True)
minerData['emptyBlock'].fillna(0, inplace=True)
emptyUncles = minerData['emptyUncle'].sum()


#define reward for uncleBlocks
for index, row in minerData.iterrows():
    incDelay = minerData.loc[index, 'incDelay']
    if row['uncle'] == 1:    
        minerData.loc[index, 'blockAward'] = (8-incDelay)/8 * 5
        minerData.loc[index, 'blockAwardwoFee'] = (8-incDelay)/8 * 5
avgBlockAward = minerData['blockAward'].mean()
avgUncleAward = minerData.loc[minerData['uncle']==1, 'blockAward'].mean()
totalUncles = minerData.loc[minerData['uncle']==1, 'uncle'].sum()



# find empty block uncle rate

totemptyBlocks = len(minerData.loc[minerData['gasUsed']==0])
emptyMains =  len(minerData.loc[(minerData['gasUsed']==0) & (minerData['main']==True)])
emptyUnclePct = emptyUncles/float(totemptyBlocks)
print (totemptyBlocks, emptyUncles, emptyMains)
print ("%.3f" % (emptyUnclePct))


# Create uncle dataframe to summarize uncle stats
uncleBlocks = pd.DataFrame(minerData.loc[minerData['uncle'] == 1]) 
uncleBlocks['incDelay']= uncleBlocks['includedBlockNum'] - uncleBlocks['blockNum']
uncleBlocks['uncleAward'] = (8-uncleBlocks['incDelay'])/8 * 5
avgUncleAward = uncleBlocks['uncleAward'].mean()
totalUncles = len(uncleBlocks)
minerUncleBlocks = uncleBlocks.groupby('miner').sum()

#clean
minerUncleBlocks = minerUncleBlocks.drop(['id', 'blockNum', 'gasLimit', 'uncsReported', 'main', 'mainIdents', 'uncleIdents', 'includedBlockNum', 'incDelay', 'blockFee', 'includeFee', 'blockAward', 'blockAwardwoFee', 'mgasUsed', 'emptyBlock'], axis=1)

minerUncleBlocks = minerUncleBlocks.rename(columns={'gasUsed': 'uncleGasUsed'})

# Create mainchain dataframe to summarize mined blocks
mainBlocks = pd.DataFrame(minerData.loc[minerData['uncle']==0])
avgMainRewardwoFee = mainBlocks['blockAwardwoFee'].mean()
avgMainRewardwFee = mainBlocks['blockAward'].mean()
avgBlockFee = mainBlocks['blockFee'].mean()
totalMainBlocks = len(mainBlocks)

#create summary table
minerBlocks = mainBlocks.groupby('miner').sum()
minerBlocks = minerBlocks.drop(['id', 'blockNum', 'gasLimit', 'includedBlockNum', 'duplicates','mainIdents', 'uncle', 'emptyUncle'], axis=1)


# Merge the two tables on miner
minerBlocks = minerBlocks.join(minerUncleBlocks)
minerBlocks['uncleAward'].fillna(0, inplace = True)
minerBlocks['uncle'].fillna(0, inplace = True)
minerBlocks['totReward'] = minerBlocks['blockAward'] + minerBlocks['uncleAward']

#calc miner totals
minerBlocks['totalBlocks'] = minerBlocks['main'] + minerBlocks['uncle']
minerBlocks['mainAwardwFee'] = minerBlocks['blockAward']/minerBlocks['main']
minerBlocks['avgBlockFee'] = minerBlocks['blockFee']/minerBlocks['main']
minerBlocks['mainAwardwoFee'] =  minerBlocks['blockAwardwoFee'] / minerBlocks['main']
minerBlocks['uncRatio'] = minerBlocks['uncle'] / minerBlocks['totalBlocks']
minerBlocks['emptyUncRatio'] = minerBlocks['emptyUncle']/(minerBlocks['emptyUncle']+ minerBlocks['emptyBlock'])
minerBlocks['avgUncleAward'] = minerBlocks['uncleAward'] / minerBlocks['uncle']
minerBlocks['avgGasUsed'] = (minerBlocks['gasUsed'] + minerBlocks['uncleGasUsed'])/minerBlocks['totalBlocks']
minerBlocks['avgTxFee'] = minerBlocks['avgBlockFee']/minerBlocks['avgGasUsed']*1e9
minerBlocks['avgReward'] = minerBlocks['totReward'] / minerBlocks['totalBlocks']
minerBlocks = minerBlocks.sort_values('totalBlocks', ascending = False)


# Regression model for gas
minerData['const'] = 1
model = sm.OLS(minerData['uncle'], minerData[['const','mgasUsed']])
results = model.fit()
print (results.summary())
dictResults = dict(results.params)

mainUncleDiff = avgUncleAward - avgMainRewardwoFee
breakeven = -1*dictResults['mgasUsed']/1e6 * mainUncleDiff * 1e9
print(breakeven)

#find Profit
expectedEmptyAward = (avgMainRewardwoFee*(1-dictResults['const'])) + (avgUncleAward*dictResults['const'])
predictedUncle = dictResults['const'] + (dictResults['mgasUsed'] * totAvgGasUsed/1e6)
expectedTxAward = (avgMainRewardwFee*(1-predictedUncle)) + (avgUncleAward*predictedUncle)

profit = expectedTxAward - expectedEmptyAward
profitpct = profit/avgBlockFee
profitpctBlock = profit/avgMainRewardwFee
#create Dataframe


resultTable = {
    'miner': ['all'],
    'totalBlocks': [totalBlocks],
    'uncles': [totalUncles],
    'emptyUncles':[emptyUncles],
    'avgmGas': [avgMgasUsed],
    'uncRate': [uncleRate],
    'predictedUncRate': [predictedUncle],
    'zeroUncRate': [dictResults['const']],
    'actualZeroUncRate': [emptyUnclePct],
    'avgUncleReward': [avgUncleAward],
    'avgMainRewardwoFee': [avgMainRewardwoFee],
    'avgTxFees': [avgBlockFee],
    'predictEmpAward': [expectedEmptyAward],
    'predictTxAward': [expectedTxAward],
    'actualTxAward':[avgBlockAward],
    'breakeven':[breakeven],
    'profit': [profit],
    'profitPct': [profitpct],
    'profitPctBlock': [profitpctBlock]}

resultSummary = pd.DataFrame.from_dict(resultTable)
resultSummary = resultSummary[['miner', 'totalBlocks', 'uncles', 'emptyUncles', 'uncRate', 'predictedUncRate', 'avgmGas','zeroUncRate', 'actualZeroUncRate','avgUncleReward', 'avgMainRewardwoFee', 'avgTxFees', 'predictEmpAward', 'predictTxAward', 'actualTxAward', 'breakeven', 'profit', 'profitPct', 'profitPctBlock']]

miningpoolgas = minerBlocks.loc['0xb2930b35844a230f00e51431acae96fe543a0347', 'avgGasUsed']
miningpoolfee = minerBlocks.loc['0xb2930b35844a230f00e51431acae96fe543a0347', 'avgBlockFee']
topMiners = minerBlocks.head(n=5)

x = 1
for index, row in topMiners.iterrows(): 
    md = minerData.loc[minerData['miner']==index, :]
    model = sm.OLS(md['uncle'], md[['const', 'mgasUsed']])
    results = model.fit()
    dictResults = dict(results.params)
    predictedUncle = dictResults['const'] + (dictResults['mgasUsed'] * row['avgGasUsed']/1e6)
    mpoolUncle = dictResults['const'] + (dictResults['mgasUsed'] * miningpoolgas/1e6)
    mpoolAward = ((row['mainAwardwoFee']+miningpoolfee)*(1-mpoolUncle)) + (row['avgUncleAward']*mpoolUncle)
    expectedEmptyAward = (row['mainAwardwoFee']*(1-dictResults['const'])) + (row['avgUncleAward']*dictResults['const'])
    expectedTxAward = (row['mainAwardwFee']*(1-predictedUncle)) + (row['avgUncleAward']*predictedUncle)
    mainUncleDiff = row['avgUncleAward'] - row['mainAwardwoFee']
    breakeven = -1*dictResults['mgasUsed']/1e6 * mainUncleDiff * 1e9
    resultSummary.loc[x, 'miner'] = index
    resultSummary.loc[x, 'totalBlocks'] = row['totalBlocks']
    resultSummary.loc[x, 'uncles'] = row['uncle']
    resultSummary.loc[x, 'emptyUncles'] = row['emptyUncle']
    resultSummary.loc[x, 'avgmGas'] = row['avgGasUsed']/1e6
    resultSummary.loc[x, 'uncRate'] = row['uncRatio']
    resultSummary.loc[x, 'predictedUncRate'] = predictedUncle
    resultSummary.loc[x, 'zeroUncRate'] = dictResults['const']
    resultSummary.loc[x, 'actualZeroUncRate'] = row['emptyUncRatio']
    resultSummary.loc[x, 'avgUncleReward'] = row['avgUncleAward']
    resultSummary.loc[x, 'avgMainRewardwoFee'] = row['mainAwardwoFee']
    resultSummary.loc[x, 'avgTxFees'] = row['avgBlockFee']
    resultSummary.loc[x, 'predictEmpAward'] = expectedEmptyAward
    resultSummary.loc[x, 'predictTxAward'] = expectedTxAward
    resultSummary.loc[x, 'actualTxAward'] = row['avgReward']
    resultSummary.loc[x, 'profit'] = row['avgReward'] - expectedEmptyAward
    resultSummary.loc[x, 'profitPct'] = (row['avgReward'] - expectedEmptyAward)/ row['avgBlockFee']
    resultSummary.loc[x, 'profitPctBlock'] = (row['avgReward'] - expectedEmptyAward) / row['mainAwardwFee']
    resultSummary.loc[x, 'breakeven'] = breakeven
    resultSummary.loc[x, 'potentialAward'] = mpoolAward
    resultSummary.loc[x, 'potentialProfit'] = mpoolAward - row['avgReward']
    resultSummary.loc[x, 'avgTxFee'] = row['avgTxFee']
    print (results.summary())
    x=x+1

print(resultSummary)

for index, row in topMiners.iterrows():
    avg = minerData.loc[minerData['miner']==index, 'blockAward'].mean()
    min = minerData.loc[minerData['miner']==index, 'mgasUsed'].min()
    max = minerData.loc[minerData['miner']==index, 'mgasUsed'].max()
    med = minerData.loc[minerData['miner']==index, 'mgasUsed'].quantile(.5)
    print(index, avg, min, max, med)

