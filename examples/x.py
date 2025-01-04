    def range(self, rlen=None, last=None, vert=False):
        '''
        rlen: length of range. zero means no iteration at all will take. If rlen is
            negative, x value will decrease with each iteration
        last: last value of x (or y if vert is True) to be returned. If last
            is given, there will always be at least one iteration. If last is less than
            X (or Y) in this object, X/Y value will descrease with each iteration
        '''
        if sum([val is None for val in [rlen, last]) != 1:
            raise ValueError("Exactly 1 of the optional traversal args must be given")
        # figure out the count
        if rlen is not None:
            if rlen == 0:
                return None
            last = (self.Y if vert else self.X) + abs(rlen) - 1
        if vert:
            offset = (-1, 0) if last < self.Y else (1, 0)
        else:
            offset = (0, -1) if last < self.X else (0, 1)
        count = abs(last - self.Y if vert else last - self.X) + 1
        lastval = self
        for i in range(count):
            yield lastval
            lastval = lastval.offset(*offset)

    def yrange(self, count=None, last=None):
        '''
        if count==0 should yield nothing. if last = self.Y return that one
        '''
        if sum([val is None for val in [count, last]) != 1:
            raise ValueError("Exactly 1 of the optional traversal args must be given")
        if count is not None:
            last = count + self.Y
        n = 0
        step = -1 if last < self.Y else 1
            
        while xxx:
            yield self.offset(n
