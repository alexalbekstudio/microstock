from moviepy import VideoFileClip, AudioFileClip, CompositeAudioClip
import moviepy.video.fx as vfx

def montiraj_video():
    print("Učitavam priloženi video i novi glas...")
    
    # 1. Učitavanje videa i vašeg novog audio zapisa
    video = VideoFileClip("generisani_video.mp4")
    glas = AudioFileClip("moj_glas.mp3")

    # 2. Sinhronizacija trajanja: video prati dužinu glasa + 0.5s pauze na kraju
    trajanje = glas.duration + 0.5

    if video.duration < trajanje:
        # Ponavlja video (loop) ako je kraći od govora
        video = video.with_effects([vfx.Loop(duration=trajanje)])
    else:
        # Skraćuje video tačno na trajanje govora
        video = video.subclipped(0, trajanje)

    # 3. Postavljanje glasa na video
    finalni_audio = CompositeAudioClip([glas])
    finalni_video = video.with_audio(finalni_audio)

    # 4. Renderovanje finalnog MP4 fajla
    print("Renderujem finalni promotivni video...")
    finalni_video.write_videofile(
        "MicroStock_Gotov_Reel.mp4",
        codec="libx264",
        audio_codec="aac",
        fps=30
    )

    # Oslobađanje resursa
    video.close()
    glas.close()
    finalni_video.close()

    print("\nUspjeh! Gotov video je spreman: 'MicroStock_Gotov_Reel.mp4'")

if __name__ == "__main__":
    montiraj_video()