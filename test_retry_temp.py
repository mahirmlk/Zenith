import asyncio
import sys
sys.path.insert(0, 'backend')
from services.retry import async_retry

async def test():
    # Test 1: Does not retry on ValueError
    call_count = 0
    async def func_value():
        nonlocal call_count
        call_count += 1
        raise ValueError('not retried')

    try:
        await async_retry(func_value, max_retries=2, base_delay=0.01)
        print('FAIL: Should have raised ValueError')
    except ValueError as e:
        if 'not retried' in str(e) and call_count == 1:
            print('PASS: ValueError not retried (count=1)')
        else:
            print(f'FAIL: ValueError count={call_count}')

    # Test 2: Does retry on ConnectionError
    call_count2 = 0
    async def func_conn():
        nonlocal call_count2
        call_count2 += 1
        if call_count2 < 3:
            raise ConnectionError('retry me')
        return 'success'

    try:
        result = await async_retry(func_conn, max_retries=3, base_delay=0.01)
        if result == 'success' and call_count2 == 3:
            print('PASS: ConnectionError retried correctly (count=3)')
        else:
            print(f'FAIL: ConnectionError result={result} count={call_count2}')
    except Exception as e:
        print(f'FAIL: Unexpected exception {e}')

if __name__ == '__main__':
    asyncio.run(test())
