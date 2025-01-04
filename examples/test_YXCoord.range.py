def test_range(y,x,**args):
    yx = YXCoord(y,x)
    print (f"Testing: {yx} -> {args}")
    try:
        for yx2 in yx.range(**args):
            print (f"  {yx2}")
    except Exception as e:
        print(f"Failed: {e}")
    
if __name__ == "__main__":
    # curses.wrapper
    test_range(1,2,rlen=3)
    test_range(0,0,rlen=-3)
    test_range(3,4,rlen=-3)
    test_range(3,4,rlen=0)
    test_range(3,4,rlen=2,last=5) #fail
    test_range(1,2,rlen=3,vert=True)
    test_range(0,0,rlen=-3,vert=True)
    test_range(3,4,rlen=-3,vert=True)
    test_range(3,4,rlen=0,vert=True)
