// Explicit design fixtures. No score, record or rank in this file is live NBA data.
export const TEAMS = Object.freeze([
 ['BOS','Boston Celtics','East',19,5],['CLE','Cleveland Cavaliers','East',18,6],['NYK','New York Knicks','East',16,8],['ORL','Orlando Magic','East',15,9],['MIL','Milwaukee Bucks','East',14,10],['IND','Indiana Pacers','East',14,10],['MIA','Miami Heat','East',13,11],['DET','Detroit Pistons','East',12,12],['ATL','Atlanta Hawks','East',11,13],['CHI','Chicago Bulls','East',10,14],['PHI','Philadelphia 76ers','East',9,15],['TOR','Toronto Raptors','East',8,16],['BKN','Brooklyn Nets','East',7,17],['CHA','Charlotte Hornets','East',6,18],['WAS','Washington Wizards','East',4,20],
 ['OKC','Oklahoma City Thunder','West',20,4],['DEN','Denver Nuggets','West',18,6],['MIN','Minnesota Timberwolves','West',17,7],['HOU','Houston Rockets','West',16,8],['LAL','Los Angeles Lakers','West',15,9],['GSW','Golden State Warriors','West',14,10],['SAS','San Antonio Spurs','West',14,10],['LAC','Los Angeles Clippers','West',13,11],['DAL','Dallas Mavericks','West',12,12],['SAC','Sacramento Kings','West',11,13],['PHX','Phoenix Suns','West',10,14],['MEM','Memphis Grizzlies','West',9,15],['POR','Portland Trail Blazers','West',8,16],['NOP','New Orleans Pelicans','West',6,18],['UTA','Utah Jazz','West',5,19],
].map(([code,name,conference,wins,losses])=>Object.freeze({code,name,conference,wins,losses})));
export const SETS = Object.freeze([
 [ ['feature','BOS','LAL',118,112],['g02','NYK','BKN',108,99],['g03','OKC','DEN',121,116],['g04','GSW','HOU',104,110] ],
 [ ['g05','MIL','MIA',113,109],['g06','MIN','SAS',107,114],['g07','CLE','ORL',119,106],['g08','LAC','DAL',102,111] ],
 [ ['g09','PHI','TOR',106,101],['g10','DET','CHI',115,112],['g11','SAC','PHX',122,120],['g12','POR','MEM',98,105] ],
].map(set=>Object.freeze(set.map(([id,home,away,homeScore,awayScore])=>Object.freeze({id,home,away,homeScore,awayScore})))));
export const team = code => TEAMS.find(t=>t.code===code);
export const game = id => SETS.flat().find(g=>g.id===id);
