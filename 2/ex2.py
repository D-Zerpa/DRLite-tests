list_1 = []

with open('2\input2.txt', 'r') as cal: 
    for line in cal.readlines():
        list_1.append(line.split())

safe = []

for report in list_1:
    for level, next in zip(report, report[1:]):
        if level 
    
def safety_check(l):
    safe = []
    for level, next in zip(l, l[1:]):
        if level >= next and (level = next+1 or level = next+2 or level = next+3):
            


print()