def clamp (x):
    if x > 5:
        x = 5
    elif x < -5:
        x = -5
    return x
    

print(clamp(78))