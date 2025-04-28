import asyncio


def run_async_loop(loop):
    """
    주어진 asyncio 이벤트 루프를 현재 스레드의 이벤트 루프로 설정하고 실행합니다.
    루프가 종료될 때 정리 작업을 수행합니다.

    Args:
        loop: 실행할 asyncio 이벤트 루프 객체.
    """
    asyncio.set_event_loop(loop)
    try:
        print("비동기 이벤트 루프 시작...")
        loop.run_forever()
    finally:
        print("비동기 이벤트 루프 종료 중...")
        if not loop.is_closed():
            loop.close()
        print("비동기 이벤트 루프 종료 완료.")


if __name__ == "__main__":

    async def sample_task():
        print("샘플 비동기 작업 실행 중...")
        await asyncio.sleep(1)
        print("샘플 비동기 작업 완료.")

    test_loop = asyncio.new_event_loop()
    asyncio.run_coroutine_threadsafe(sample_task(), test_loop)

    print("테스트: 루프를 2초간 실행합니다.")
    test_loop.call_later(2, test_loop.stop)
    run_async_loop(test_loop)
    print("테스트 루프 종료됨.")
